"""会话级模型覆盖的回归测试：字段读写、ChatService 遵循、API PATCH。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai_config.models import AIConfig
from apps.projects.models import Conversation
from apps.projects.serializers import ConversationSerializer
from services.chat_service import ChatService
from services.encryption_service import get_encryption


class ModelOverrideTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="override-user", password="x")
        AIConfig.objects.create(
            user=self.user,
            provider="openai",
            api_key_encrypted=get_encryption().encrypt("sk-test"),
            base_url="https://api.example.com/v1",
            model_name="base-model",
        )
        self.service = ChatService(self.user)

    def _conversation(self, override=""):
        return Conversation.objects.create(user=self.user, title="t", model_override=override)

    def test_config_uses_global_model_without_override(self):
        config = self.service._get_config(conversation=self._conversation())
        self.assertEqual(config.model_name, "base-model")

    def test_config_applies_conversation_override(self):
        config = self.service._get_config(conversation=self._conversation("better-model"))
        self.assertEqual(config.model_name, "better-model")
        # 覆盖只影响内存副本，不落库
        self.assertEqual(AIConfig.objects.get(user=self.user).model_name, "base-model")

    def test_compat_agent_builds_with_override_model(self):
        agent = self.service._get_compat_agent(self._conversation("better-model"))
        self.assertEqual(agent.model, "better-model")
        self.assertEqual(agent.config.base_url, "https://api.example.com/v1")

    def test_blank_override_ignored(self):
        config = self.service._get_config(conversation=self._conversation("   "))
        self.assertEqual(config.model_name, "base-model")

    def test_serializer_roundtrip(self):
        conversation = self._conversation()
        serializer = ConversationSerializer(conversation, data={"model_override": "x-model"}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(user=self.user)
        conversation.refresh_from_db()
        self.assertEqual(conversation.model_override, "x-model")
