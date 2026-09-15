"""知识库检索：上传文件分块向量化入库，聊天时按相似度召回注入上下文。

- 向量化优先走用户配置的 embeddings 接口；无配置时降级为本地哈希向量，
  召回质量下降但链路不断。
- 召回是“尽力而为”：索引未建好、检索出错都只记录日志，绝不阻断聊天。
"""
from __future__ import annotations

import hashlib
import logging
import math

import numpy as np

from apps.files.models import FileChunk
from services.ai_service import AIService

logger = logging.getLogger("api")

EMBED_DIM = 256
EMBED_BATCH = 32
MAX_INDEX_CHARS = 60000
QUERY_CHAR_BUDGET = 500
TOP_K = 6
RESULT_CHAR_BUDGET = 2600

_rag_embedder = None


def _get_rag_embedder():
    global _rag_embedder
    if _rag_embedder is None:
        _rag_embedder = RagEmbedder()
    return _rag_embedder


class RagEmbedder:
    """单例 embedding 提供方：配置可用走 API，否则本地哈希向量。"""

    def __init__(self):
        self.mode = "hash"
        self.embedding_model = ""
        self._ai_service = None
        self._ready = False

    def _ensure_ready(self):
        if self._ready:
            return
        self._ready = True
        try:
            from apps.ai_config.models import AIConfig

            config = AIConfig.objects.filter(is_active=True).first()
        except Exception:
            config = None
        if not config or getattr(config, "provider", "") == "anthropic":
            return
        self._ai_service = AIService(config)
        self.embedding_model = getattr(config, "embedding_model_name", "") or ""
        if self.embedding_model:
            self.mode = "api"

    def is_api_ready(self):
        self._ensure_ready()
        return self.mode == "api"

    def dim(self):
        self._ensure_ready()
        return len(self.embed_one("维度探测"))

    def embed_one(self, text):
        return self.embed_many([text])[0]

    def embed_many(self, texts):
        self._ensure_ready()
        if self.mode == "api":
            try:
                return self._api_embed(texts)
            except Exception as exc:
                logger.warning("Embeddings API failed (%s), falling back to local hash vectors", exc)
        return [_hash_embed(text, EMBED_DIM) for text in texts]

    def _api_embed(self, texts):
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            response = self._ai_service.client.embeddings.create(
                model=self.embedding_model,
                input=batch,
            )
            vectors.extend(np.asarray(item.embedding, dtype=np.float32) for item in response.data)
        return vectors


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
    """按行切分带重叠的文本块，尽量不切在句子中间。"""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    chunks = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) > target:
            chunks.append(current)
            current = (current[-overlap:] + "\n" + line) if overlap else line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def index_uploaded_file(uploaded):
    """把上传文件抽文本、分块、向量化并落库；返回是否成功索引。"""
    FileChunk.objects.filter(file=uploaded).delete()
    text = _extract_index_text(uploaded)
    chunks = chunk_text_for_index(text[:MAX_INDEX_CHARS])
    if not chunks:
        return False

    embedder = _get_rag_embedder()
    vectors = embedder.embed_many(chunks)
    FileChunk.objects.bulk_create([
        FileChunk(
            file=uploaded,
            user=uploaded.user,
            file_name=uploaded.original_name,
            chunk_index=index,
            content=chunk,
            embedding=np.asarray(vector, dtype=np.float32).tobytes(),
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ])
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
    """按查询向量召回相关块，返回 (注入的上下文字符串, 命中块数)。"""
    query = (query or "").strip()[:QUERY_CHAR_BUDGET]
    if not query:
        return "", 0
    rows = list(FileChunk.objects.filter(user=user).only("file_name", "content", "embedding"))
    if not rows:
        return "", 0

    embedder = _get_rag_embedder()
    query_vector = embedder.embed_one(query)
    matrix = np.stack([np.frombuffer(row.embedding, dtype=np.float32) for row in rows])
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1e-12
    scores = (matrix @ query_vector) / (np.linalg.norm(query_vector) or 1e-12) / norms

    top_indices = np.argsort(scores)[::-1][: max(k * 2, k)]
    picked = []
    used_chars = 0
    per_file = {}
    for index in top_indices:
        row = rows[int(index)]
        score = float(scores[int(index)])
        # 哈希向量分数天然偏低，阈值只拦“明显无关”
        threshold = 0.2 if embedder.is_api_ready() else 0.06
        if score < threshold:
            continue
        if per_file.get(row.file_name, 0) >= 2:
            continue
        snippet = row.content
        if used_chars + len(snippet) > char_budget:
            snippet = snippet[: max(0, char_budget - used_chars)].strip()
            if not snippet:
                break
        picked.append((row, snippet))
        used_chars += len(snippet)
        per_file[row.file_name] = per_file.get(row.file_name, 0) + 1
        if len(picked) >= k or used_chars >= char_budget:
            break

    if not picked:
        return "", 0

    lines = [
        "以下是与用户问题相关的已上传资料片段（来自你的知识库，可直接引用并注明文件名）：",
        "",
    ]
    for row, snippet in picked:
        lines.append(f"[来源: {row.file_name}]")
        lines.append(snippet)
        lines.append("")
    return "\n".join(lines).strip(), len(picked)
