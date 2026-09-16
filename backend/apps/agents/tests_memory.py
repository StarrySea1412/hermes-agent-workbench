"""自动记忆的回归测试：抽取解析、去重、召回、注入组装。"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agents.models import AgentMemory
from services import memory_service
from services.memory_service import (
    _parse_extraction,
    _extract_and_store,
    build_memory_prompt,
    recall_memories,
)


class ParseExtractionTests(TestCase):
    def test_plain_json(self):
        items = _parse_extraction('[{"title": "偏好", "content": "喜欢液态玻璃风"}]')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "偏好")

    def test_json_in_code_fence_and_prose(self):
        raw = '好的，以下是记忆：\n```json\n[{"title": "a", "content": "b"}]\n```'
        self.assertEqual(len(_parse_extraction(raw)), 1)

    def test_garbage_returns_empty(self):
        self.assertEqual(_parse_extraction("没有可记的内容"), [])
        self.assertEqual(_parse_extraction('{"title": "x"}'), [])


class ExtractAndStoreTests(TestCase):
    def setUp(self):
        from apps.ai_config.models import AIConfig
        from services.encryption_service import get_encryption

        self.user = get_user_model().objects.create_user(username="mem-user", password="x")
        AIConfig.objects.create(
            user=self.user,
            provider="openai",
            api_key_encrypted=get_encryption().encrypt("sk-x"),
            base_url="https://api.example.com/v1",
            model_name="m1",
        )

    def test_short_reply_skipped(self):
        with mock.patch("services.ai_service.AIService") as ai:
            count = _extract_and_store(self.user, "帮我把 X 记住", "好的。")
        self.assertEqual(count, 0)
        ai.assert_not_called()

    def test_extracts_and_dedupes(self):
        extraction = [
            {"title": "项目背景", "content": "用户在做 AI-skill 工作台，走液态玻璃风"},
            {"title": "偏好", "content": "喜欢克制的视觉，不要实色面板"},
        ]
        with mock.patch("services.ai_service.AIService") as ai:
            ai.return_value.generate_content.return_value = "```json\n" + _dumps(extraction) + "\n```"
            count = _extract_and_store(self.user, "介绍一下我的项目偏好", "x" * 300)

        self.assertEqual(count, 2)
        self.assertEqual(AgentMemory.objects.filter(user=self.user).count(), 2)
        auto = AgentMemory.objects.filter(user=self.user, metadata__source="auto")
        self.assertEqual(auto.count(), 2)

        # 同样的内容再来一轮：去重后不再新增
        with mock.patch("services.ai_service.AIService") as ai:
            ai.return_value.generate_content.return_value = _dumps(extraction)
            second = _extract_and_store(self.user, "再说说我的项目偏好", "y" * 300)
        self.assertEqual(second, 0)


class RecallTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="recall-user", password="x")

    def test_pinned_first_and_prompt_assembly(self):
        AgentMemory.objects.create(
            user=self.user, title="部署", content="生产环境用 Postgres，通过 DB_ENGINE 切换",
            scope="user", pinned=True, metadata={"source": "auto"},
        )
        AgentMemory.objects.create(
            user=self.user, title="无关", content="完全不相干的记录内容完全没有重叠词汇",
            scope="user", metadata={"source": "auto"},
        )
        picked = recall_memories(self.user, "生产环境数据库用什么")
        self.assertEqual(picked[0][0], "部署")

        prompt = build_memory_prompt(self.user, "生产环境数据库用什么")
        self.assertIn("长期记忆", prompt)
        self.assertIn("Postgres", prompt)

    def test_no_memories_empty_prompt(self):
        self.assertEqual(build_memory_prompt(self.user, "任意问题"), "")

    def test_user_isolation(self):
        other = get_user_model().objects.create_user(username="other-mem", password="x")
        AgentMemory.objects.create(user=other, title="秘密", content="另一个用户的记忆", scope="user")
        self.assertEqual(build_memory_prompt(self.user, "秘密"), "")

    def test_extraction_thread_wired_via_views_helper(self):
        # _extract_memories_async 存在且可调用（不起真线程，只验导入与签名）
        from apps.projects.views import _extract_memories_async

        self.assertTrue(callable(_extract_memories_async))


def _dumps(items):
    import json

    return json.dumps(items, ensure_ascii=False)
