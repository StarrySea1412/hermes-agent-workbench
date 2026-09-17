"""知识库检索：上传文件分块向量化入库，聊天时按相似度召回注入上下文。

- 向量化优先走用户配置的 embeddings 接口；无配置时降级为本地哈希向量，
  召回质量下降但链路不断。
- 召回是“尽力而为”：索引未建好、检索出错都只记录日志，绝不阻断聊天。
"""
from __future__ import annotations

import hashlib
import logging
import math
import re

import numpy as np

from django.db import transaction

from apps.files.models import FileChunk
from services.ai_service import AIService

logger = logging.getLogger("api")

EMBED_DIM = 256
EMBED_BATCH = 32
MAX_INDEX_CHARS = 60000
QUERY_CHAR_BUDGET = 500
TOP_K = 6
RESULT_CHAR_BUDGET = 2600

# BinaryField 内的版本化封装：magic + 模型指纹 + float32 向量，无需 schema 迁移。
# 无此前缀的历史向量无法证明模型兼容，只允许词法召回。
_EMBED_MAGIC = b"RAG\x01"


def _get_rag_embedder(user):
    return RagEmbedder(user)


class RagEmbedder:
    """每次操作按当前用户取配置；哈希只表示词法信号，不是语义 embedding。"""

    def __init__(self, user):
        self.user = user
        self.mode = "hash"
        self.embedding_model = ""
        self.model_fingerprint = None
        self._ai_service = None
        self._ready = False

    def _ensure_ready(self):
        if self._ready:
            return
        self._ready = True
        try:
            from apps.ai_config.models import AIConfig

            config = AIConfig.objects.filter(user=self.user, is_active=True).first()
            if not config or config.provider == "anthropic" or not config.embedding_model_name.strip():
                return
            self._ai_service = AIService(config)
            self.embedding_model = config.embedding_model_name.strip()
            identity = "\n".join((
                str(self.user.pk), config.provider,
                (config.base_url or "").strip().rstrip("/"), self.embedding_model,
            ))
            self.model_fingerprint = hashlib.sha256(identity.encode("utf-8")).digest()
            self.mode = "api"
        except Exception:
            logger.exception("Embedding configuration unavailable for user_id=%s", self.user.pk)

    def is_api_ready(self):
        self._ensure_ready()
        return self.mode == "api"

    def embed_one(self, text):
        return self.embed_many([text])[0]

    def embed_many(self, texts):
        self._ensure_ready()
        if self.mode == "api":
            try:
                return self._api_embed(texts)
            except Exception as exc:
                logger.warning("Embeddings API failed (%s), falling back to lexical hash vectors", exc)
                # 不能把失败后的哈希向量标为此 API 模型的语义向量。
                self.mode = "hash"
                self.model_fingerprint = None
        return [_hash_embed(text, EMBED_DIM) for text in texts]

    def _api_embed(self, texts):
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            response = self._ai_service.client.embeddings.create(
                model=self.embedding_model,
                input=batch,
            )
            items = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in items] != list(range(len(batch))):
                raise ValueError("Embedding response indices/count do not match input")
            vectors.extend(np.asarray(item.embedding, dtype=np.float32) for item in items)
        if vectors and any(
            vector.ndim != 1 or not vector.size or vector.shape != vectors[0].shape
            or not np.all(np.isfinite(vector)) or not np.linalg.norm(vector)
            for vector in vectors
        ):
            raise ValueError("Embedding response contains invalid vectors")
        return vectors


def _encode_embedding(vector, fingerprint):
    payload = np.asarray(vector, dtype=np.float32).tobytes()
    return _EMBED_MAGIC + fingerprint + payload if fingerprint else payload


def _tokenize(text):
    """中英文混合切词：英文按空格，CJK 按字符 + 相邻二字组。"""
    tokens = []
    for word in (text or "").lower().split():
        if not any("一" <= ch <= "鿿" for ch in word):
            tokens.append(word)
            continue
        cjk_chars = [ch for ch in word if "一" <= ch <= "鿿"]
        tokens.extend(cjk_chars)
        tokens.extend("".join(cjk_chars[i:i + 2]) for i in range(len(cjk_chars) - 1))
    return tokens


def _hash_embed(text, dim):
    """本地哈希向量：把 token 散列进固定维度后 L2 归一化。"""
    tokens = _tokenize(text) or [text[:24]]
    vector = np.zeros(dim, dtype=np.float32)
    for token in tokens:
        digest = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "little")
        vector[digest % dim] += 1.0 if digest >> 63 else -1.0
    norm = math.sqrt(float(vector @ vector))
    if norm:
        vector /= norm
    return vector


def chunk_text_for_index(text, target=900, overlap=160):
    """标题是硬章节边界；章内优先按行、长单行按字符切分，严格限制块长。"""
    if target <= 0 or not 0 <= overlap < target:
        raise ValueError("Require target > 0 and 0 <= overlap < target")
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    sections = []
    current_section = []
    for line in lines:
        if re.match(r"^#{1,6}\s", line) and current_section:
            sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append(current_section)

    chunks = []
    for section in sections:
        section_text = "\n".join(section)
        start = 0
        while start < len(section_text):
            end = min(start + target, len(section_text))
            if end < len(section_text):
                boundary = section_text.rfind("\n", start, end + 1)
                # 不把章首标题单独切走；短边界也不值得牺牲块容量。
                heading_end = len(section[0]) if start == 0 and re.match(r"^#{1,6}\s", section[0]) else -1
                if boundary > max(start + overlap, start + target // 2, heading_end):
                    end = boundary
            chunk = section_text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(section_text):
                break
            start = end - overlap
    return chunks


def index_uploaded_file(uploaded):
    """把上传文件抽文本、分块、向量化并落库；返回是否成功索引。

    先算好再事务性替换分块：抽取或向量化失败时保留旧索引。
    """
    text = _extract_index_text(uploaded)
    chunks = chunk_text_for_index(text[:MAX_INDEX_CHARS])
    if not chunks:
        return False

    embedder = _get_rag_embedder(uploaded.user)
    vectors = embedder.embed_many(chunks)
    if len(vectors) != len(chunks):
        raise ValueError("Embedding count does not match chunks")
    fingerprint = embedder.model_fingerprint
    new_chunks = [
        FileChunk(
            file=uploaded,
            user=uploaded.user,
            file_name=uploaded.original_name,
            chunk_index=index,
            content=chunk,
            embedding=_encode_embedding(vector, fingerprint),
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    with transaction.atomic():
        FileChunk.objects.filter(file=uploaded).delete()
        FileChunk.objects.bulk_create(new_chunks)
    return True


def _extract_index_text(uploaded):
    """抽出可索引文本，单独成函数便于测试替身。"""
    from services.document_analyzer import DocumentAnalyzer

    try:
        if uploaded.file:
            return DocumentAnalyzer().extract_text(uploaded.file.path) or ""
    except Exception as exc:
        logger.warning("Index text extraction failed for %s: %s", uploaded.original_name, exc)
    return ""


def delete_file_chunks(file_id):
    FileChunk.objects.filter(file_id=file_id).delete()


def retrieve_context(user, query, k=TOP_K, char_budget=RESULT_CHAR_BUDGET):
    """模型指纹一致的语义分 + 本地词法哈希分；历史未知模型仅用词法。

    返回 (注入文本, 命中块数, 来源列表[{file_id, file, chunks}])。
    file 是展示名，同名文件附加 ID 消歧。
    """
    query = (query or "").strip()[:QUERY_CHAR_BUDGET]
    if not query or k <= 0 or char_budget <= 0:
        return "", 0, []
    rows = list(FileChunk.objects.filter(user=user, file__user=user).only(
        "file_id", "file_name", "content", "embedding",
    ).order_by("file_id", "chunk_index", "id"))
    if not rows:
        return "", 0, []

    embedder = _get_rag_embedder(user)
    query_vector = embedder.embed_one(query)
    lexical_query = _hash_embed(query, EMBED_DIM)

    names = {}
    for row in rows:
        names.setdefault(row.file_name, set()).add(row.file_id)
    labels = {
        row.file_id: (f"{row.file_name} (file_id={row.file_id})"
                      if len(names[row.file_name]) > 1 else row.file_name)
        for row in rows
    }
    candidates = []
    for row in rows:
        lexical = max(float(_hash_embed(row.content, EMBED_DIM) @ lexical_query), 0.0)
        semantic, available = _stored_semantic_score(row, query_vector, embedder.model_fingerprint)
        score = 0.65 * max(semantic, 0.0) + 0.35 * lexical if available else lexical
        # 阈值跟随实际评分方式，而不是“配置了 API”。
        if score >= (0.15 if available else 0.08):
            candidates.append((score, row))
    candidates.sort(key=lambda pair: -pair[0])

    picked = []
    used_chars = 0
    sources = {}
    for score, row in candidates:
        if sources.get(row.file_id, 0) >= 2:
            continue
        snippet = row.content[:max(0, char_budget - used_chars)].strip()
        if not snippet:
            continue
        picked.append((row, snippet))
        used_chars += len(snippet)
        sources[row.file_id] = sources.get(row.file_id, 0) + 1
        if len(picked) >= k or used_chars >= char_budget:
            break

    if not picked:
        return "", 0, []

    lines = [
        "以下是与用户问题相关的已上传资料片段（来自你的知识库，可直接引用并注明来源）：",
        "",
    ]
    for row, snippet in picked:
        lines.append(f"[来源: {labels[row.file_id]}]")
        lines.append(snippet)
        lines.append("")
    context = "\n".join(lines).strip()
    source_list = [
        {"file_id": file_id, "file": labels[file_id], "chunks": count}
        for file_id, count in sources.items()
    ]
    return context, len(picked), source_list


def _stored_semantic_score(row, query_vector, fingerprint=None):
    """只有带当前用户/端点/模型指纹的向量可作语义评分，裸历史向量不可信。"""
    if not fingerprint:
        return 0.0, False
    payload = bytes(row.embedding)
    prefix = _EMBED_MAGIC + fingerprint
    if not payload.startswith(prefix) or len(payload) != len(prefix) + len(query_vector) * 4:
        return 0.0, False
    vector = np.frombuffer(payload[len(prefix):], dtype=np.float32)
    norm = float(np.linalg.norm(vector) * np.linalg.norm(query_vector))
    if not norm or not math.isfinite(norm):
        return 0.0, False
    score = float(vector @ query_vector / norm)
    return (score, True) if math.isfinite(score) else (0.0, False)
