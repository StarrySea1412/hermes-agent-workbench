"""RAG 知识库的回归测试：分块、本地向量、索引落库、召回、设置字段序列化。"""
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
        rag_service._rag_embedder = None
        self.user = get_user_model().objects.create_user(username="rag-user", password="x")
        self.uploaded = UploadedFile.objects.create(
            user=self.user,
            original_name="产品规划.md",
            file_type="md",
            file_size=64,
        )

    def tearDown(self):
        rag_service._rag_embedder = None

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

        context, count = retrieve_context(self.user, "沙箱 执行 画图")
        self.assertGreater(count, 0)
        self.assertIn("沙箱", context)
        self.assertIn("产品规划.md", context)

    def test_retrieve_is_scoped_to_user(self):
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            index_uploaded_file(self.uploaded)

        other = get_user_model().objects.create_user(username="other-user", password="x")
        context, count = retrieve_context(other, "沙箱")
        self.assertEqual(count, 0)
        self.assertEqual(context, "")

    def test_unrelated_query_returns_empty(self):
        with mock.patch("services.rag_service._extract_index_text", return_value=self._mock_text()):
            index_uploaded_file(self.uploaded)
        context, count = retrieve_context(self.user, "quantum chromodynamics lattice gauge")
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
