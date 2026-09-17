import json
import logging
import os
import re

from apps.agents.models import AgentRun
from apps.ai_config.models import AIConfig
from apps.projects.models import Message
from apps.tools import registry, schemas
from services.ai_service import AIService, describe_ai_exception
from services.chat_cancel import is_chat_cancelled
from services.document_analyzer import DocumentAnalyzer
from services.hermes_service import build_session_id, create_hermes_service
from services.tool_call_parser import parse_tool_calls
from services.tool_loop import run_tool_loop, summarize_tool_result

logger = logging.getLogger("api")

CHAT_SYSTEM_PROMPT = """You are Hermes Chat running on Hermes Gateway.
Respond in Chinese when the user writes Chinese.

Your job is to produce usable work, not status narration. Prefer concrete deliverables:
- files, tables, checklists, plans, patches, summaries, or next actions;
- concise assumptions when data is missing;
- explicit limitations only when they affect the result.

Use tools when they improve correctness:
- If files are attached, inspect them with doc_parse before making claims.
- If fresh public information is required, call web_search. Do not claim web results unless the tool succeeded.
- If the user asks for Excel, XLSX, spreadsheet, CSV-like output, or a table file, call doc_export with format="xlsx".
- For calculation, data wrangling, quick simulations, or rendering charts, call python_sandbox. Charts: use matplotlib with the Agg backend and save .png files in the working directory.
- When the user asks for a web page, dashboard mock, poster, or interactive visualization, output one complete standalone HTML artifact in a ```html code block: inline CSS/JS, no external assets or CDNs, so it renders in the sandboxed preview.
- For user-facing file exports, use only provided tools such as doc_export. Do not ask for Python, shell, write_file, or execute_code permissions.

Output style:
- Put the answer or artifact link first.
- Use short headings and compact bullets.
- For tables, use Markdown tables.
- Do not explain internal implementation unless the user asks."""

MODE_INSTRUCTIONS = {
    "chat": "Treat this as an ongoing working session. Move the task forward and produce the most useful next artifact.",
    "deck": "When the user asks for slides, produce slide titles, bullets, notes, and export-ready structure.",
    "report": "When the user asks for a report, produce clear sections, evidence notes, and delivery-ready prose.",
}

MODE_TOOL_NAMES = {
    "chat": ["doc_parse", "web_search", "doc_export", "python_sandbox"],
    "deck": ["doc_parse", "web_search", "doc_export", "python_sandbox"],
    "report": ["doc_parse", "web_search", "doc_export", "python_sandbox"],
}

MAX_HERMES_TURNS = 6

UPSTREAM_FAILURE_MARKERS = (
    "api call failed",
    "api_connection_error",
    "apiconnectionerror",
    "apitimeouterror",
    "authenticationerror",
    "ratelimiterror",
    "permissiondeniederror",
    "error code:",
    "connection error",
    "connection refused",
    "connecterror",
    "certificate verify failed",
    "rate limit exceeded",
    "insufficient_quota",
    "quota exceeded",
    "invalid api key",
    "bad gateway",
)


class GatewayUpstreamFailure(RuntimeError):
    """Hermes gateway returned an upstream failure message instead of a model answer."""


def _gateway_reply_failure(reply):
    content = (reply or "").strip()
    lowered = content.lower()
    if not content or len(content) > 400:
        return None
    if not any(marker in lowered for marker in UPSTREAM_FAILURE_MARKERS):
        return None
    return f"Hermes gateway returned an upstream failure instead of an answer: {content[:200]}"


class ChatService:
    def __init__(self, user):
        self.user = user

    def build_reasoning_trace(self, conversation, user_content, attachment_ids=None):
        session_id = self.get_session_id(conversation)
        files = self.get_context_files(conversation, attachment_ids=attachment_ids)
        tool_names = self.resolve_tool_names(conversation)
        mode_label = {
            "chat": "连续对话",
            "deck": "演示文稿",
            "report": "报告文档",
        }.get(conversation.mode, "交付物")
        project_title = conversation.project.title if conversation.project else conversation.title

        return [
            {
                "title": "接入 Hermes 会话",
                "content": f"当前会话绑定到 {session_id}，围绕“{project_title}”继续处理本轮请求。",
            },
            {
                "title": "装载上下文",
                "content": f"已装载 {len(files)} 份资料，并保留当前对话历史作为 Hermes 输入。",
            },
            {
                "title": "准备工具策略",
                "content": f"本轮允许 Hermes 按需调用 {', '.join(tool_names) if tool_names else '无工具'}，优先先取证再回答。",
            },
            {
                "title": "生成本轮结果",
                "content": f"按“{mode_label}”模式继续推进，并把回答整理成可继续编辑的输出。用户请求：{user_content[:120]}",
            },
        ]

    def build_context(self, conversation, attachment_ids=None, rag_sources=None):
        """AIService 直连路径的上下文：附件摘要 + 知识库召回片段。"""
        files = self.get_context_files(conversation, attachment_ids=attachment_ids)
        parts = []
        if files:
            parts.append(DocumentAnalyzer().summarize_for_context(files))
        try:
            from services.rag_service import retrieve_context

            last_user = ""
            for message in reversed(list(conversation.messages.order_by("created_at"))):
                if message.role == "user" and message.content:
                    last_user = message.content
                    break
            if last_user:
                retrieved, _count, sources = retrieve_context(self.user, last_user)
                if retrieved:
                    parts.append(retrieved)
                    if rag_sources is not None:
                        rag_sources.extend(sources)
        except Exception:
            logger.exception("Knowledge retrieval failed in build_context: conversation_id=%s", conversation.id)
        return "\n\n".join(part for part in parts if part)

    def get_context_files(self, conversation, attachment_ids=None):
        files = []
        seen = set()

        if conversation.project_id:
            for link in conversation.project.project_files.select_related("file"):
                file_obj = link.file
                if not file_obj or file_obj.id in seen:
                    continue
                seen.add(file_obj.id)
                files.append(file_obj)

        if attachment_ids:
            for file_obj in self.user.uploaded_files.filter(id__in=attachment_ids):
                if file_obj.id in seen:
                    continue
                seen.add(file_obj.id)
                files.append(file_obj)

        return files

    def get_history(self, conversation, extra_user_message=None):
        messages = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages.order_by("created_at")
            if message.role in {"user", "assistant"}
        ]
        if extra_user_message:
            messages.append({"role": "user", "content": extra_user_message})
        return messages

    def get_session_id(self, conversation):
        if conversation.project_id:
            session_id = build_session_id(self.user.id, conversation.project_id)
            if session_id:
                return session_id
        return f"u{self.user.id}-c{conversation.id}"

    def resolve_tool_names(self, conversation):
        return MODE_TOOL_NAMES.get(conversation.mode, MODE_TOOL_NAMES["chat"])

    def generate_reply(self, conversation, user_content, attachment_ids=None):
        reply = ""
        metadata = {}
        for event, data in self.stream_turn(conversation, user_content, attachment_ids=attachment_ids):
            if event == "done":
                reply = data.get("reply", "")
                metadata = data.get("metadata", {})
        return reply, metadata

    def stream_turn(self, conversation, user_content, attachment_ids=None):
        session_id = self.get_session_id(conversation)
        files = self.get_context_files(conversation, attachment_ids=attachment_ids)
        base_history = self.get_history(conversation)
        tool_names = self.resolve_tool_names(conversation)
        tool_events = []
        used_tools = []
        thoughts = []
        agent_run = None
        try:
            agent_run = self._start_chat_agent_run(conversation, user_content, files, session_id)
        except Exception:
            logger.exception("Failed to create AgentRun for conversation_id=%s", conversation.id)

        compat = self._get_compat_agent(conversation)
        prefer_compat = compat is not None and os.getenv("CHAT_PREFER_GATEWAY", "").lower() not in ("1", "true", "yes")
        hermes = create_hermes_service(session_id=session_id)

        yield "status", {
            "stage": "session_ready",
            "gateway": "compat" if prefer_compat else "hermes",
            "session_id": session_id,
            "mode": conversation.mode,
            "file_count": len(files),
            "tool_names": tool_names,
            "agent_run_id": getattr(agent_run, "id", None),
        }

        for thought in self.build_reasoning_trace(conversation, user_content, attachment_ids=attachment_ids):
            thoughts.append(thought)
            yield "thought", thought

        if prefer_compat:
            finished = yield from self._try_compat_then_hermes(
                compat,
                hermes,
                conversation,
                base_history,
                files,
                session_id,
                tool_names,
                thoughts,
                tool_events,
                used_tools,
                agent_run,
            )
        else:
            finished = yield from self._try_hermes_then_compat(
                hermes,
                compat,
                conversation,
                base_history,
                files,
                session_id,
                tool_names,
                thoughts,
                tool_events,
                used_tools,
                agent_run,
            )
        if finished:
            return

        if agent_run is not None:
            try:
                from django.utils import timezone
                agent_run.update_status_atomic(
                    "failed",
                    error="Fell back to local reply; upstream chat unavailable.",
                    completed_at=timezone.now(),
                    tools_used=list(used_tools),
                )
            except Exception:
                logger.exception("Failed to mark chat AgentRun failed")

        rag_sources = []
        reply = self._fallback_or_ai_reply(
            conversation, user_content, attachment_ids=attachment_ids,
            allow_ai=not compat, rag_sources=rag_sources,
        )
        metadata = {
            **self.extract_delivery_metadata(reply),
            "gateway": "fallback",
            "session_id": session_id,
            "model_name": self._get_runtime_model_name(),
            "mode": conversation.mode,
            "thoughts": thoughts,
            "tool_events": tool_events,
            "used_tools": used_tools,
            "file_count": len(files),
            "agent_run_id": getattr(agent_run, "id", None),
        }
        if rag_sources:
            metadata["rag_sources"] = rag_sources
        for chunk in chunk_text(reply):
            yield "delta", {"content": chunk}
        yield "done", {"reply": reply, "metadata": metadata}

    def _try_compat_then_hermes(
        self,
        compat,
        hermes,
        conversation,
        base_history,
        files,
        session_id,
        tool_names,
        thoughts,
        tool_events,
        used_tools,
        agent_run,
    ):
        """有账号模型配置时优先直连中转站：思考链可直读，网关作为后备。"""
        if compat:
            try:
                yield from self._stream_agent_reply(
                    compat, conversation, list(base_history), files, session_id, tool_names,
                    thoughts, tool_events, used_tools, gateway_label="compat", agent_run=agent_run,
                )
                return True
            except Exception as exc:
                logger.exception("Compatible chat turn failed: conversation_id=%s user_id=%s", conversation.id, self.user.id)
                yield "status", {
                    "stage": "gateway_resume",
                    "gateway": "hermes",
                    "session_id": session_id,
                    "message": f"当前账号模型不可用，已切换 Hermes 网关继续执行：{_format_runtime_error(exc)}",
                    "diagnostic": describe_ai_exception(exc),
                }
        if hermes:
            try:
                yield from self._stream_agent_reply(
                    hermes, conversation, list(base_history), files, session_id, tool_names,
                    thoughts, tool_events, used_tools, gateway_label="hermes", agent_run=agent_run,
                )
                return True
            except Exception as exc:
                logger.exception("Hermes chat turn failed: conversation_id=%s user_id=%s", conversation.id, self.user.id)
                yield "status", {
                    "stage": "fallback",
                    "gateway": "fallback",
                    "session_id": session_id,
                    "message": f"Hermes 网关也不可用，已回退到本地保底答复：{_format_runtime_error(exc)}",
                    "diagnostic": describe_ai_exception(exc),
                }
        return False

    def _try_hermes_then_compat(
        self,
        hermes,
        compat,
        conversation,
        base_history,
        files,
        session_id,
        tool_names,
        thoughts,
        tool_events,
        used_tools,
        agent_run,
    ):
        """旧行为：网关优先（CHAT_PREFER_GATEWAY=1 时启用）。"""
        if hermes:
            try:
                yield from self._stream_agent_reply(
                    hermes, conversation, list(base_history), files, session_id, tool_names,
                    thoughts, tool_events, used_tools, gateway_label="hermes", agent_run=agent_run,
                )
                return True
            except Exception as exc:
                logger.exception("Hermes chat turn failed: conversation_id=%s user_id=%s", conversation.id, self.user.id)
                yield "status", {
                    "stage": "compat_resume",
                    "gateway": "compat",
                    "session_id": session_id,
                    "message": f"Hermes 网关当前不可用，已切换到当前账号模型继续执行：{_format_runtime_error(exc)}",
                    "diagnostic": describe_ai_exception(exc),
                }
        if compat:
            try:
                yield from self._stream_agent_reply(
                    compat, conversation, list(base_history), files, session_id, tool_names,
                    thoughts, tool_events, used_tools, gateway_label="compat", agent_run=agent_run,
                )
                return True
            except Exception as exc:
                logger.exception("Compatible chat turn failed: conversation_id=%s user_id=%s", conversation.id, self.user.id)
                yield "status", {
                    "stage": "fallback",
                    "gateway": "fallback",
                    "session_id": session_id,
                    "message": f"当前账号模型也不可用，已回退到本地保底答复：{_format_runtime_error(exc)}",
                    "diagnostic": describe_ai_exception(exc),
                }

    def save_user_message(self, conversation, content, attachment_ids=None):
        metadata = {"attachments": attachment_ids or []}
        return Message.objects.create(conversation=conversation, role="user", content=content, metadata=metadata)

    def save_assistant_message(self, conversation, content, metadata=None):
        return Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=content,
            metadata=metadata or self.extract_delivery_metadata(content),
        )

    def extract_delivery_metadata(self, content):
        outline = []
        for line in (content or "").splitlines():
            stripped = line.strip(" -#\t")
            if not stripped:
                continue
            if "页" in stripped or "slide" in stripped.lower() or stripped[:2].isdigit():
                outline.append(stripped[:160])
        return {"outline": outline[:12]}

    def sync_project_from_reply(self, conversation, assistant_content):
        project = conversation.project
        if not project:
            return
        metadata = self.extract_delivery_metadata(assistant_content)
        outline = metadata.get("outline") or project.outline
        project.outline = outline
        project.final_content = assistant_content
        project.status = "writing"
        project.save(update_fields=["outline", "final_content", "status", "updated_at"])

    def _build_file_prompt(self, files):
        if not files:
            return ""

        lines = [
            "Attached files available in this conversation:",
        ]
        for file_obj in files[:8]:
            line = (
                f"- file_id={file_obj.id} | {file_obj.original_name} | "
                f"type={file_obj.file_type} | size={file_obj.file_size_display}"
            )
            if file_obj.description:
                line = f"{line} | note={file_obj.description[:120]}"
            lines.append(line)
        lines.append("Use doc_parse with a file_id when you need the real file contents.")
        return "\n".join(lines)

    def _build_retrieval_prompt(self, conversation, history):
        """从知识库按本轮问题召回相关片段；任何失败都返回 (空, [])，不阻断聊天。"""
        try:
            from services.rag_service import retrieve_context

            query = ""
            for message in reversed(history or []):
                if message.get("role") == "user" and message.get("content"):
                    query = message["content"]
                    break
            if not query:
                return "", []
            context, _count, sources = retrieve_context(self.user, query)
            if not context:
                return "", []
            return f"\n\n{context}", sources
        except Exception:
            logger.exception("Knowledge retrieval failed: conversation_id=%s", conversation.id)
            return "", []

    def _build_memory_prompt(self, conversation, history):
        """召回跨会话长期记忆；失败返回空不阻断聊天。"""
        try:
            from services.memory_service import build_memory_prompt

            query = ""
            for message in reversed(history or []):
                if message.get("role") == "user" and message.get("content"):
                    query = message["content"]
                    break
            return build_memory_prompt(self.user, query)
        except Exception:
            logger.exception("Memory recall failed: conversation_id=%s", conversation.id)
            return ""

    def _build_system_prompt(self, conversation, file_prompt="", tools_prompt="", memory_prompt=""):
        project = conversation.project
        project_note = ""
        if project and project.description:
            project_note = f"Workspace note:\n{project.description[:1200]}"

        sections = [
            CHAT_SYSTEM_PROMPT,
            MODE_INSTRUCTIONS.get(conversation.mode, MODE_INSTRUCTIONS["chat"]),
            project_note,
            memory_prompt,
            file_prompt,
            tools_prompt,
        ]
        return "\n\n".join(section for section in sections if section).strip()

    def _fallback_or_ai_reply(self, conversation, user_content, attachment_ids=None, allow_ai=True, rag_sources=None):
        config = self._get_config(conversation=conversation)
        if not config or not allow_ai:
            return self._fallback_reply(conversation, user_content)
        context = self.build_context(conversation, attachment_ids=attachment_ids, rag_sources=rag_sources)
        messages = self.get_history(conversation)
        return AIService(config).generate_content(messages, system_prompt=CHAT_SYSTEM_PROMPT, context=context)

    def _get_config(self, conversation=None):
        try:
            config = AIConfig.objects.get(user=self.user, is_active=True)
        except AIConfig.DoesNotExist:
            return None
        override = (getattr(conversation, "model_override", "") or "").strip()
        if override:
            # 会话级模型覆盖：只换模型名，provider/base_url/密钥沿用全局配置（内存内改写，不落库）
            config.model_name = override
        return config

    def _get_runtime_model_name(self, agent=None):
        config = self._get_config()
        config_model = getattr(config, "model_name", "") if config else ""
        if config_model:
            return config_model
        return getattr(agent, "model", "") or ""

    def _get_runtime_base_url(self, agent=None):
        config = self._get_config()
        return (getattr(config, "base_url", "") or "") if config else ""

    def _fallback_reply(self, conversation, user_content):
        title = conversation.project.title if conversation.project else conversation.title
        session_id = self.get_session_id(conversation)
        files = self.get_context_files(conversation)
        tool_names = self.resolve_tool_names(conversation)
        return f"""Hermes 运行时这一轮暂时不可用，我先按当前会话状态把任务接住。

## 当前任务
{user_content[:500]}

## 当前上下文
1. 会话：{session_id}
2. 空间：{title}
3. 资料：{len(files)} 份
4. 工具：{", ".join(tool_names) if tool_names else "无"}

## 建议下一步
1. {("继续让我读取现有资料并提炼关键点。" if files else "先上传资料，或把目标、受众、截止时间补充清楚。")}
2. 明确你希望的输出形态：结论、方案、README、PRD、设计稿、汇报提纲都可以。
3. 我会继续按“理解 -> 证据 -> 结构 -> 下一步”的方式推进，而不是停在一次性回答。"""

    def _get_compat_agent(self, conversation=None):
        config = self._get_config(conversation=conversation)
        if not config:
            return None
        try:
            return AIService(config)
        except Exception as exc:
            logger.warning("Compatible AI service unavailable for user_id=%s: %s", self.user.id, exc)
            return None

    def _stream_agent_reply(
        self,
        agent,
        conversation,
        history,
        files,
        session_id,
        tool_names,
        thoughts,
        tool_events,
        used_tools,
        gateway_label,
        agent_run=None,
    ):
        """真流式：tool_loop 在后台线程跑，事件实时经队列透传为 SSE。"""
        import queue
        import threading

        file_prompt = self._build_file_prompt(files)
        # 知识库召回：从已向量化资料里按本轮问题取相关片段；失败静默不阻断聊天
        retrieval_prompt, rag_sources = self._build_retrieval_prompt(conversation, history)
        # 长期记忆召回：跨会话沉淀的用户事实
        memory_prompt = self._build_memory_prompt(conversation, history)
        # MCP 动态工具（仅本地执行链路）：发现 → 放行名字 → 注入 function 定义
        extra_tools = []
        if gateway_label == "compat":
            try:
                from services.mcp_client import get_user_mcp_tools, to_openai_tool

                mcp_tools = get_user_mcp_tools(self.user)
                extra_tools = [to_openai_tool(tool) for tool in mcp_tools]
                tool_names = list(tool_names) + [tool["prefixed"] for tool in mcp_tools]
            except Exception:
                logger.exception("MCP tool collection failed: conversation_id=%s", conversation.id)
        extra_headers = {"X-Hermes-Session-Id": session_id} if gateway_label == "compat" and session_id else None
        event_queue: queue.Queue = queue.Queue()
        DONE = object()

        if rag_sources:
            chunk_total = sum(source["chunks"] for source in rag_sources)
            yield "status", {
                "stage": "rag_recall",
                "message": f"知识库召回 {chunk_total} 条相关片段（{'、'.join(source['file'] for source in rag_sources)}）",
            }

        def build_system_prompt(native_tools_enabled, tools_prompt_text):
            return self._build_system_prompt(
                conversation,
                file_prompt + retrieval_prompt,
                "" if native_tools_enabled else tools_prompt_text,
                memory_prompt=memory_prompt,
            )

        def on_event(event_type, payload):
            event_queue.put((event_type, payload))
            if event_type == "thought":
                thoughts.append(payload)
            elif event_type == "tool_call":
                name = payload.get("name") or ""
                if name and name not in used_tools:
                    used_tools.append(name)
                if payload not in tool_events:
                    tool_events.append(payload)
            elif event_type == "tool_result" and agent_run is not None:
                self._record_tool_step(agent_run, payload)

        tool_context = {
            "user": self.user,
            "user_id": self.user.id,
            "project_id": conversation.project_id,
            "conversation_id": conversation.id,
            "run_id": getattr(agent_run, "id", None),
        }

        def run_loop():
            try:
                loop_result = run_tool_loop(
                    agent=agent,
                    history=history,
                    tool_names=tool_names,
                    build_system_prompt=build_system_prompt,
                    tool_context=tool_context,
                    max_turns=MAX_HERMES_TURNS,
                    extra_headers=extra_headers,
                    extra_tools=extra_tools,
                    on_event=on_event,
                    should_cancel=lambda: is_chat_cancelled(conversation.id),
                )
                event_queue.put(("__result__", loop_result))
            except Exception as exc:
                event_queue.put(("__error__", exc))
            finally:
                event_queue.put(DONE)

        worker = threading.Thread(target=run_loop, daemon=True)
        worker.start()

        loop_result = None
        stream_error = None
        while True:
            item = event_queue.get()
            if item is DONE:
                break
            event_type, payload = item
            if event_type == "__result__":
                loop_result = payload
                continue
            if event_type == "__error__":
                stream_error = payload
                continue
            if event_type == "status":
                yield "status", {
                    "stage": payload.get("stage") or "tool_fallback",
                    "gateway": gateway_label,
                    "session_id": session_id,
                    "message": payload.get("message", ""),
                }
            elif event_type == "thought":
                yield "thought", payload
            elif event_type == "thought_delta":
                yield "thought_delta", payload
            elif event_type == "answer_delta":
                yield "answer_delta", payload
            elif event_type == "tool_call":
                yield "tool_call", payload
            elif event_type == "tool_result":
                yield "tool_result", payload

        if stream_error is not None:
            raise stream_error
        if loop_result is None:
            raise RuntimeError("Tool loop finished without a result.")

        # 用户停止：tool_loop 在下一个轮次/工具边界返回空回复，这里按中断处理
        # 而不是走"空回复"错误路径
        if is_chat_cancelled(conversation.id):
            from services.chat_cancel import TurnCancelled

            raise TurnCancelled("已由用户停止本轮生成。")

        for name in loop_result.used_tools:
            if name not in used_tools:
                used_tools.append(name)

        # 网关路径回合后取证：生命周期事件只有工具名+状态，
        # 真实参数与执行结果在运行时会话历史里，按 call_id 回填
        if gateway_label == "hermes" and tool_events and getattr(agent, "session_id", None):
            self._enrich_tool_events(agent, tool_events)

        if loop_result.exhausted:
            raise RuntimeError(f"Hermes exhausted {MAX_HERMES_TURNS} turns without a final answer.")

        # 空回复：模型只有思考没有正文。带诊断提示而不是无声吞掉，方便用户重试或调整模型。
        reply = loop_result.reply
        if not reply:
            raise RuntimeError(
                "模型这轮只输出了思考内容，没有生成正文。请重新发送，或在设置页换一个模型 / 调大输出上限。"
            )
        if gateway_label == "hermes":
            failure_message = _gateway_reply_failure(reply)
            if failure_message:
                raise GatewayUpstreamFailure(failure_message)
        if gateway_label == "hermes" and _looks_like_gateway_tool_block(reply):
            raise RuntimeError("Hermes gateway stopped on internal file-execution permissions.")

        if agent_run is not None:
            from django.utils import timezone

            agent_run.update_status_atomic(
                "done",
                answer=reply,
                tools_used=list(used_tools),
                completed_at=timezone.now(),
            )

        metadata = {
            **self.extract_delivery_metadata(reply),
            "gateway": gateway_label,
            "session_id": session_id,
            "model_name": self._get_runtime_model_name(agent),
            "base_url": self._get_runtime_base_url(agent),
            "mode": conversation.mode,
            "thoughts": thoughts,
            "tool_events": tool_events,
            "used_tools": used_tools,
            "file_count": len(files),
            "agent_run_id": getattr(agent_run, "id", None),
        }
        if rag_sources:
            metadata["rag_sources"] = rag_sources
        for chunk in chunk_text(reply):
            yield "delta", {"content": chunk}
        yield "done", {"reply": reply, "metadata": metadata}

    def _enrich_tool_events(self, agent, tool_events):
        """用网关会话历史回填工具事件的真实参数与执行结果（尽力而为）。"""
        try:
            trace = agent.fetch_session_tool_trace()
        except Exception:
            logger.exception("Tool trace enrichment failed")
            return
        if not trace:
            return
        for event in tool_events:
            record = trace.get(event.get("id") or "")
            if not record:
                continue
            if record.get("args"):
                event["args"] = record["args"]
            result_content = record.get("result_content")
            if result_content:
                # 剥掉运行时包的 <untrusted_tool_result> 声明壳，只留工具原始输出
                inner = re.search(
                    r"<untrusted_tool_result[^>]*>([\s\S]*?)</untrusted_tool_result>",
                    result_content,
                )
                if inner:
                    result_content = inner.group(1)
                event["result"] = {
                    "ok": event.get("status") != "error",
                    "result": str(result_content).strip()[:4000],
                }

    def _record_tool_step(self, agent_run, payload):
        if agent_run is None:
            return
        try:
            from apps.agents.orchestrator import _emit_step

            order = (agent_run.step_count or 0) + 1
            _emit_step(
                agent_run,
                order=order,
                step_type="tool_result",
                status=payload.get("status") or "ok",
                tool_name=payload.get("name") or "",
                tool_args=payload.get("args") or {},
                tool_result=payload.get("result"),
                thought=payload.get("thought") or "",
            )
        except Exception:
            logger.exception("Failed to record tool step for run_id=%s", getattr(agent_run, "id", None))

    def _start_chat_agent_run(self, conversation, user_content, files, session_id):
        file_ids = [f.id for f in files if getattr(f, "id", None)]
        return AgentRun.objects.create(
            user=self.user,
            task=user_content,
            status="running",
            session_id=session_id or "",
            file_ids=file_ids,
            conversation=conversation,
            source="chat_turn",
            max_steps=MAX_HERMES_TURNS,
        )



def chunk_text(text, size=24):
    text = text or ""
    for index in range(0, len(text), size):
        yield text[index:index + size]


def _looks_like_gateway_tool_block(text):
    content = (text or "").lower()
    if not content:
        return False
    permission_markers = [
        "permission",
        "execute_code",
        "write_file",
        "python",
        "权限",
        "写文件",
        "执行",
    ]
    deliverable_markers = ["xlsx", "excel", "文件", "导出"]
    return any(marker in content for marker in permission_markers) and any(
        marker in content for marker in deliverable_markers
    )


def _format_runtime_error(exc):
    details = describe_ai_exception(exc)
    message = details.get("message") or str(exc)
    error_type = details.get("error_type")
    hint = details.get("hint")
    parts = [message]
    if error_type:
        parts.append(f"类型：{error_type}")
    if hint:
        parts.append(f"建议：{hint}")
    return "；".join(parts)


def summarize_tool_result(result):
    if not isinstance(result, dict):
        return str(result)[:180]
    if not result.get("ok"):
        return str(result.get("error") or "工具执行失败。")[:180]

    payload = result.get("result")
    if isinstance(payload, dict):
        if "filename" in payload and "text" in payload:
            return f"已读取 {payload.get('filename')}，返回 {len(payload.get('text') or '')} 个字符。"
        if "results" in payload:
            return f"已返回 {len(payload.get('results') or [])} 条搜索结果。"
        if "filename" in payload and "url" in payload:
            return f"已导出 {payload.get('filename')}。"
    return json.dumps(payload, ensure_ascii=False)[:180] if payload is not None else "工具执行完成。"
