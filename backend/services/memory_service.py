"""聊天自动记忆：回合结束后轻量抽取长期事实，下一轮召回注入。

- 抽取：用用户配置的模型跑一次小提示词，输出 JSON 数组；无配置/开关关闭/
  回复过短都跳过。后台线程执行，绝不阻断聊天。
- 去重：与该用户现有记忆做哈希向量相似度（词袋级），>0.82 视为重复。
- 召回：置顶优先，其余按与当前问题的哈希相似度排序；命中即回写 last_used_at。
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("api")

MIN_REPLY_CHARS = 200
MAX_MEMORIES_PER_TURN = 3
RECALL_LIMIT = 4
DEDUPE_THRESHOLD = 0.82
MAX_MEMORY_CHARS = 500
AUTO_MEMORY_ENABLED_ENV = "CHAT_AUTO_MEMORY"

EXTRACT_SYSTEM_PROMPT = """你是记忆管家。从这轮对话里提炼值得长期记住的事实，供以后的对话参考：
- 用户的长期偏好、背景、称呼习惯
- 正在推进的项目及其稳定约束
- 用户明确要求记住的事

不要记一次性细节（今天天气、这条消息怎么措辞）、不要记对话过程本身。
只输出 JSON 数组，每项 {"title": "≤20字标题", "content": "一句话事实"}，最多 3 条；没有就输出 []。"""


def auto_memory_enabled():
    import os

    return os.getenv(AUTO_MEMORY_ENABLED_ENV, "1").lower() not in ("0", "false", "no")


def extract_and_store_memories(user, conversation_id, user_content, assistant_reply):
    """回合结束后调用（后台线程）：抽取→去重→落库。任何失败静默。"""
    from django.db import connections

    try:
        stored = _extract_and_store(user, user_content, assistant_reply)
        if stored:
            logger.info("Auto memories stored: user_id=%s conversation_id=%s count=%s", user.id, conversation_id, stored)
    except Exception:
        logger.exception("Memory extraction failed: user_id=%s conversation_id=%s", user.id, conversation_id)
    finally:
        connections.close_all()


def _extract_and_store(user, user_content, assistant_reply) -> int:
    if not auto_memory_enabled():
        return 0
    reply = (assistant_reply or "").strip()
    if len(reply) < MIN_REPLY_CHARS or not (user_content or "").strip():
        return 0

    from apps.ai_config.models import AIConfig
    from services.ai_service import AIService

    config = AIConfig.objects.filter(user=user, is_active=True).first()
    if not config:
        return 0

    messages = [
        {"role": "user", "content": f"用户说：\n{str(user_content)[:1500]}\n\n助手回答（节选）：\n{reply[:2500]}"}
    ]
    raw = AIService(config).generate_content(
        messages,
        system_prompt=EXTRACT_SYSTEM_PROMPT,
        context="",
    )
    items = _parse_extraction(raw)
    if not items:
        return 0

    from apps.agents.models import AgentMemory

    existing = list(
        AgentMemory.objects.filter(user=user, scope="user")
        .values_list("title", "content")
    )
    existing_vectors = [(_hash(text), ) for text in [f"{title}\n{content}" for title, content in existing]]

    stored = 0
    for item in items[:MAX_MEMORIES_PER_TURN]:
        title = str(item.get("title") or "").strip()[:120]
        content = str(item.get("content") or "").strip()[:MAX_MEMORY_CHARS]
        if not content:
            continue
        vector = _hash(f"{title}\n{content}")
        if any(_cosine(vector, vec[0]) > DEDUPE_THRESHOLD for vec in existing_vectors):
            continue
        AgentMemory.objects.create(
            user=user,
            title=title or content[:24],
            content=content,
            scope="user",
            tags=["auto"],
            metadata={"source": "auto"},
        )
        existing.append((title, content))
        existing_vectors.append((vector,))
        stored += 1
    return stored


def _parse_extraction(raw):
    text = str(raw or "").strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def recall_memories(user, query, limit=RECALL_LIMIT):
    """返回 [(title, content)]：置顶优先，其余按与 query 的哈希相似度。"""
    from apps.agents.models import AgentMemory

    rows = list(
        AgentMemory.objects.filter(user=user, scope="user")
        .order_by("-pinned", "-last_used_at", "-updated_at")
        .values("id", "title", "content", "pinned")[:60]
    )
    if not rows:
        return []

    query_vector = _hash(query)
    scored = []
    for row in rows:
        vector = _hash(f"{row['title']}\n{row['content']}")
        scored.append((_cosine(query_vector, vector), row))
    scored.sort(key=lambda pair: (not pair[1]["pinned"], -pair[0]))

    picked = [(row["id"], row["title"], row["content"]) for _, row in scored[:limit]]
    if picked:
        try:
            from django.utils import timezone

            AgentMemory.objects.filter(id__in=[item[0] for item in picked]).update(
                last_used_at=timezone.now()
            )
        except Exception:
            pass
    return [(item[1], item[2]) for item in picked]


def build_memory_prompt(user, query):
    """召回长期记忆并组装注入段；任何失败返回空字符串。"""
    try:
        if not (query or "").strip():
            return ""
        memories = recall_memories(user, query)
        if not memories:
            return ""
        lines = ["以下是关于这位用户的长期记忆（跨会话沉淀，供你自然参考，不必逐条复述）：", ""]
        for title, content in memories:
            lines.append(f"- {title}：{content}")
        return "\n".join(lines)
    except Exception:
        logger.exception("Memory recall failed")
        return ""


def _hash(text):
    from services.rag_service import _hash_embed

    return _hash_embed(text, 256)


def _cosine(a, b):
    import numpy as np

    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    if not norm:
        return 0.0
    return float(np.asarray(a) @ np.asarray(b) / norm)
