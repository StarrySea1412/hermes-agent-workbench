"""RAG 知识库的回归测试：分块、本地向量、索引落库、召回、设置字段序列化。"""
from types import SimpleNamespace
from unittest import mock

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai_config.serializers import AIConfigSerializer, AIConfigUpdateSerializer
from apps.files.models import FileChunk, UploadedFile
from services import rag_service
from services.rag_service import (
    _hash_embed,
    chunk_text_for_index,
    index_uploaded_file,
    retrieve_context,
)


class ChunkingTests(SimpleTestCase):
    def test_splits_on_line_boundaries(self):
        text = "\n".join(f"段落{i} " + "内容" * 100 for i in range(12))
        chunks = chunk_text_for_index(text, target=500, overlap=60)
        self.assertGreater(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 500 + 120)

    def test_short_text_single_chunk(self):
        self.assertEqual(chunk_text_for_index("  短短一句。\n"), ["短短一句。"])
        self.assertEqual(chunk_text_for_index(""), [])

    def test_markdown_headings_start_new_chunks(self):
        # 每个章节都撑到 target 以上，才能验证标题硬边拆开（小文档本来就该并成一块）
        body = ("正文内容充满整个章节，信息密度很高的技术描述。" + "细节详实、结构清晰。") * 18
        text = (
            "# 架构\n" + body + "\n"
            "# 检索\n混合检索融合语义与词法信号。\n" + body + "\n## 细节\n" + body + "\n"
        )
        chunks = chunk_text_for_index(text)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("# 架构"))
        self.assertTrue(any(chunk.startswith("# 检索") for chunk in chunks), chunks[:2])
        self.assertTrue(any("# 检索" in chunk and "混合检索" in chunk for chunk in chunks))


    def test_long_single_line_has_bounded_chunks_and_no_lost_content(self):
        text = "# 章节\n" + "abcdefghij" * 500
        chunks = chunk_text_for_index(text, target=100, overlap=20)
        self.assertTrue(all(len(chunk) <= 100 for chunk in chunks))
        self.assertTrue(chunks[0].startswith("# 章节\nabcdef"))
        self.assertEqual(chunks[0] + "".join(chunk[20:] for chunk in chunks[1:]), text)

    def test_short_sections_never_merge_or_overlap_across_headings(self):
        self.assertEqual(
            chunk_text_for_index("前言\n# A\n正文A\n## B\n正文B\n# C"),
            ["前言", "# A\n正文A", "## B\n正文B", "# C"],
        )

    def test_invalid_chunk_sizes_fail_fast(self):
        for target, overlap in [(0, 0), (10, 10), (10, -1)]:
            with self.subTest(target=target, overlap=overlap), self.assertRaises(ValueError):
                chunk_text_for_index("abc", target, overlap)


class HashEmbedTests(SimpleTestCase):
    def test_deterministic_and_normalized(self):
        a = _hash_embed("玻璃质感 设计", 256)
        b = _hash_embed("玻璃质感 设计", 256)
        np.testing.assert_array_equal(a, b)
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=5)

    def test_related_texts_score_above_unrelated(self):
        vec_a = _hash_embed("液态玻璃 界面 设计 令牌", 256)
        vec_b = _hash_embed("液态玻璃 界面 风格", 256)
        vec_c = _hash_embed("数据库 迁移 回滚 脚本", 256)
        self.assertGreater(float(vec_a @ vec_b), float(vec_a @ vec_c))


class IndexAndRetrieveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="rag-user", password="x")
        self.uploaded = UploadedFile.objects.create(
            user=self.user,
            original_name="产品规划.md",
            file_type="md",
            file_size=64,
        )

    def _mock_text(self):
        return (
            "第一期目标是把资料库接入对话，支持自动检索召回。\n" * 4
            + "\n第二期做 Python 沙箱执行，支持画图和数据计算。\n" * 4
            + "\n沙箱运行 Python 代码并回传输出。\n" * 4
            + "\n画图支持 matplotlib 出图，数据计算支持 pandas。\n" * 4
        )

    def test_index_and_retrieve_relevant_chunk(self):
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            self.assertTrue(index_uploaded_file(self.uploaded))

        self.assertGreaterEqual(FileChunk.objects.filter(file=self.uploaded).count(), 1)

        context, count, sources = retrieve_context(self.user, "沙箱 执行 画图")
        self.assertGreater(count, 0)
        self.assertIn("沙箱", context)
        self.assertIn("产品规划.md", context)
        self.assertEqual(sources, [{"file_id": self.uploaded.id, "file": "产品规划.md", "chunks": count}])

    def test_hybrid_retrieval_survives_stale_embeddings(self):
        # 旧分块 embedding 维度与当前查询不符（模拟换过模型）：词法分仍可召回
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            index_uploaded_file(self.uploaded)
        for chunk in FileChunk.objects.filter(file=self.uploaded):
            chunk.embedding = b"\x00" * 8  # 2 维，与 256 维查询不匹配
            chunk.save(update_fields=["embedding"])

        context, count, sources = retrieve_context(self.user, "沙箱 执行 画图")
        self.assertGreater(count, 0)
        self.assertIn("沙箱", context)

    def test_retrieve_is_scoped_to_user(self):
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            index_uploaded_file(self.uploaded)

        other = get_user_model().objects.create_user(username="other-user", password="x")
        context, count, sources = retrieve_context(other, "沙箱")
        self.assertEqual(count, 0)
        self.assertEqual(context, "")
        self.assertEqual(sources, [])

    def test_unrelated_query_returns_empty(self):
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            index_uploaded_file(self.uploaded)
        context, count, _sources = retrieve_context(self.user, "quantum chromodynamics lattice gauge")
        self.assertEqual(count, 0)

    def test_reindex_replaces_chunks_and_delete_cascades(self):
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            index_uploaded_file(self.uploaded)
            first_ids = set(FileChunk.objects.filter(file=self.uploaded).values_list("id", flat=True))
            index_uploaded_file(self.uploaded)
        second_ids = set(FileChunk.objects.filter(file=self.uploaded).values_list("id", flat=True))
        self.assertFalse(first_ids & second_ids)

        self.uploaded.delete()
        self.assertEqual(FileChunk.objects.filter(file_id=self.uploaded.id).count(), 0)


    def test_duplicate_file_names_have_independent_limits_and_labels(self):
        other = UploadedFile.objects.create(user=self.user, original_name=self.uploaded.original_name, file_size=1)
        for uploaded in (self.uploaded, other):
            for index in range(3):
                FileChunk.objects.create(file=uploaded, user=self.user, file_name=uploaded.original_name,
                                         chunk_index=index, content="沙箱", embedding=b"")
        context, count, sources = retrieve_context(self.user, "沙箱")
        self.assertEqual(count, 4)
        self.assertEqual({s["file_id"] for s in sources}, {self.uploaded.id, other.id})
        self.assertEqual([s["chunks"] for s in sources], [2, 2])
        self.assertEqual(len({s["file"] for s in sources}), 2)
        for source in sources:
            self.assertIn(source["file"], context)

    def test_empty_and_nonpositive_limits_return_triple(self):
        for kwargs in ({}, {"k": 0}, {"char_budget": 0}, {"k": -1}):
            self.assertEqual(retrieve_context(self.user, "", **kwargs), ("", 0, []))
        FileChunk.objects.create(file=self.uploaded, user=self.user, file_name="a", chunk_index=0,
                                 content="沙箱" * 100, embedding=b"")
        self.assertEqual(retrieve_context(self.user, "沙箱", k=0), ("", 0, []))
        context, count, sources = retrieve_context(self.user, "沙箱", char_budget=3)
        self.assertEqual(count, 1)
        self.assertIn("沙箱沙", context)
        self.assertEqual(sources[0]["chunks"], 1)

    def test_failed_reindex_preserves_existing_chunks(self):
        with mock.patch("services.rag_service._extract_index_text", return_value="沙箱"):
            index_uploaded_file(self.uploaded)
        ids = list(FileChunk.objects.values_list("id", flat=True))
        with mock.patch("services.rag_service._extract_index_text", return_value=""):
            self.assertFalse(index_uploaded_file(self.uploaded))
        self.assertEqual(list(FileChunk.objects.values_list("id", flat=True)), ids)


class EmbedderIsolationTests(TestCase):
    def setUp(self):
        from apps.ai_config.models import AIConfig

        self.user = get_user_model().objects.create_user(username="embedding-a")
        self.other = get_user_model().objects.create_user(username="embedding-b")
        self.config = AIConfig.objects.create(user=self.user, embedding_model_name="model-a")
        self.uploaded = UploadedFile.objects.create(user=self.user, original_name="a", file_size=1)
        self.api = mock.patch("services.rag_service.AIService").start()
        self.addCleanup(mock.patch.stopall)
        self.api.return_value.client.embeddings.create.side_effect = lambda **kwargs: SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=[1.0, 0.0]) for i, _ in enumerate(kwargs["input"])])

    def test_config_never_leaks_to_unconfigured_user_and_refreshes(self):
        embedder = rag_service._get_rag_embedder(self.user)
        self.assertTrue(embedder.is_api_ready())
        self.assertEqual(self.api.call_args.args[0].user_id, self.user.id)
        other = rag_service._get_rag_embedder(self.other)
        self.assertFalse(other.is_api_ready())
        self.assertIsNone(other.model_fingerprint)
        self.assertEqual(self.api.call_count, 1)
        self.config.embedding_model_name = "model-b"
        self.config.save()
        updated = rag_service._get_rag_embedder(self.user)
        updated.is_api_ready()
        self.assertNotEqual(updated.model_fingerprint, embedder.model_fingerprint)
        self.config.is_active = False
        self.config.save()
        self.assertFalse(rag_service._get_rag_embedder(self.user).is_api_ready())

    def test_same_dimension_different_model_or_endpoint_is_not_compatible(self):
        with mock.patch("services.rag_service._extract_index_text", return_value="unrelated"):
            index_uploaded_file(self.uploaded)
        with mock.patch("services.rag_service._hash_embed", return_value=np.zeros(256)):
            self.assertEqual(retrieve_context(self.user, "query")[1], 1)
            for field, value in [("embedding_model_name", "model-b"), ("base_url", "https://other.invalid/v1")]:
                with self.subTest(field=field):
                    setattr(self.config, field, value)
                    self.config.save()
                    self.assertEqual(retrieve_context(self.user, "query"), ("", 0, []))
                    setattr(self.config, field, "model-a" if field == "embedding_model_name" else "https://api.openai.com/v1")

    def test_legacy_vectors_are_lexical_only_even_with_matching_dimension(self):
        FileChunk.objects.create(file=self.uploaded, user=self.user, file_name="a", chunk_index=0,
                                 content="沙箱", embedding=np.array([1, 0], dtype=np.float32).tobytes())
        with mock.patch("services.rag_service._hash_embed", return_value=np.zeros(256)):
            self.assertEqual(retrieve_context(self.user, "query"), ("", 0, []))
        self.assertEqual(retrieve_context(self.user, "沙箱")[1], 1)

    def test_api_failure_and_bad_response_fall_back_without_semantic_tag(self):
        create = self.api.return_value.client.embeddings.create
        for effect in [RuntimeError("offline"), lambda **kw: SimpleNamespace(data=[])]:
            with self.subTest(effect=effect):
                create.side_effect = effect
                embedder = rag_service._get_rag_embedder(self.user)
                with self.assertLogs("api", level="WARNING"):
                    vectors = embedder.embed_many(["沙箱", "画图"])
                self.assertEqual(len(vectors), 2)
                self.assertEqual(embedder.mode, "hash")
                self.assertIsNone(embedder.model_fingerprint)
                row = SimpleNamespace(embedding=rag_service._encode_embedding(vectors[0], None))
                self.assertEqual(rag_service._stored_semantic_score(row, vectors[0]), (0.0, False))

    def test_api_response_order_and_corrupt_vectors(self):
        self.api.return_value.client.embeddings.create.side_effect = None
        self.api.return_value.client.embeddings.create.return_value = SimpleNamespace(data=[
            SimpleNamespace(index=1, embedding=[0, 1]), SimpleNamespace(index=0, embedding=[1, 0])])
        vectors = rag_service._get_rag_embedder(self.user).embed_many(["a", "b"])
        np.testing.assert_array_equal(vectors, [[1, 0], [0, 1]])
        fingerprint = b"a" * 32
        for vector in ([float("nan"), 0], [0, 0]):
            row = SimpleNamespace(embedding=rag_service._encode_embedding(vector, fingerprint))
            self.assertEqual(rag_service._stored_semantic_score(row, np.array([1, 0]), fingerprint), (0.0, False))


class AIConfigEmbeddingFieldTests(SimpleTestCase):
    def test_serializer_exposes_embedding_model(self):
        config = mock.Mock(
            id=1, provider="openai", base_url="https://api.example.com/v1",
            model_name="gpt-4o-mini", embedding_model_name="text-embedding-3-small",
            temperature=0.7, max_tokens=2000, is_active=True,
        )
        data = AIConfigSerializer(config).data
        self.assertEqual(data["embedding_model_name"], "text-embedding-3-small")

    def test_update_serializer_accepts_blank(self):
        serializer = AIConfigUpdateSerializer(data={"embedding_model_name": ""})
        self.assertTrue(serializer.is_valid(), serializer.errors)
