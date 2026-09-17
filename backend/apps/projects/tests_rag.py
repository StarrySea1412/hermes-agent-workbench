"""RAG 上下文、流式 done 与数据库持久化；外部模型/记忆/MCP 全部隔离。"""
import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.files.models import FileChunk, UploadedFile
from apps.projects.models import Conversation, Message
from services.chat_service import ChatService


class ChatRagTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chat-rag")
        self.client.force_authenticate(self.user)
        self.conversation = Conversation.objects.create(user=self.user, title="RAG")
        self.service = ChatService(self.user)
        uploaded = UploadedFile.objects.create(user=self.user, original_name="知识.md", file_size=1)
        FileChunk.objects.create(file=uploaded, user=self.user, file_name=uploaded.original_name,
                                 chunk_index=0, content="沙箱 画图", embedding=b"")
        self.sources = [{"file_id": uploaded.id, "file": "知识.md", "chunks": 1}]
        for target, kwargs in [
            ("services.chat_service.create_hermes_service", {"return_value": object()}),
            ("services.chat_service.ChatService._get_compat_agent", {"return_value": None}),
            ("services.chat_service.ChatService._get_config", {"return_value": None}),
            ("services.chat_service.ChatService._build_memory_prompt", {"return_value": ""}),
            ("services.chat_service.ChatService._start_chat_agent_run", {"return_value": None}),
            ("services.chat_service.is_chat_cancelled", {"return_value": False}),
            ("services.mcp_client.get_user_mcp_tools", {"return_value": []}),
            ("apps.projects.views._extract_memories_async", {"return_value": None}),
        ]:
            patcher = mock.patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.prompts = []
        patcher = mock.patch("services.chat_service.run_tool_loop", side_effect=self._loop)
        self.loop = patcher.start()
        self.addCleanup(patcher.stop)

    def _loop(self, **kwargs):
        self.prompts.append(kwargs["build_system_prompt"](True, ""))
        return SimpleNamespace(reply="检索结果", used_tools=[], exhausted=False)

    def test_stream_done_persists_real_retrieval_sources(self):
        response = self.client.post(f"/api/conversations/{self.conversation.id}/stream/",
                                    {"content": "沙箱"}, format="json")
        self.assertEqual(response.status_code, 200)
        payload = b"".join(response.streaming_content).decode()
        self.assertIn("rag_recall", payload)
        done = [json.loads(block.split("data: ", 1)[1]) for block in payload.split("\n\n")
                if block.startswith("event: done")][0]
        self.assertEqual(done["metadata"]["rag_sources"], self.sources)
        message = Message.objects.get(id=done["message_id"])
        self.assertEqual(message.metadata["rag_sources"], self.sources)
        self.assertIn("沙箱 画图", self.prompts[0])

    def test_nonstream_generate_reply_persists_sources(self):
        response = self.client.post(f"/api/conversations/{self.conversation.id}/messages/",
                                    {"content": "沙箱"}, format="json")
        self.assertEqual(response.status_code, 200)
        assistant = response.data["assistant"]
        self.assertEqual(assistant["metadata"]["rag_sources"], self.sources)
        self.assertEqual(Message.objects.get(id=assistant["id"]).metadata["rag_sources"], self.sources)

    def test_compat_done_includes_sources(self):
        events = list(self.service._stream_agent_reply(
            object(), self.conversation, [{"role": "user", "content": "沙箱"}], [],
            "session", [], [], [], [], gateway_label="compat"))
        self.assertEqual(dict(events)["done"]["metadata"]["rag_sources"], self.sources)

    def test_build_context_uses_latest_user_and_three_value_contract(self):
        self.service.save_user_message(self.conversation, "旧问题")
        self.service.save_user_message(self.conversation, "沙箱")
        self.service.save_assistant_message(self.conversation, "不用于检索")
        sources = []
        context = self.service.build_context(self.conversation, rag_sources=sources)
        self.assertIn("沙箱 画图", context)
        self.assertEqual(sources, self.sources)

    def test_no_query_and_retrieval_failure_do_not_block_chat(self):
        self.assertEqual(self.service._build_retrieval_prompt(self.conversation, []), ("", []))
        with mock.patch("services.rag_service.retrieve_context", side_effect=RuntimeError("offline")):
            with self.assertLogs("api", level="ERROR"):
                events = list(self.service._stream_agent_reply(
                    object(), self.conversation, [{"role": "user", "content": "沙箱"}], [],
                    "session", [], [], [], [], gateway_label="hermes"))
        self.assertNotIn("rag_sources", dict(events)["done"]["metadata"])
        self.assertFalse(any(data.get("stage") == "rag_recall" for event, data in events if event == "status"))

    def test_direct_ai_fallback_done_keeps_sources_but_local_fallback_does_not_retrieve(self):
        self.service.save_user_message(self.conversation, "沙箱")
        with mock.patch.object(ChatService, "_try_hermes_then_compat", return_value=iter(())), \
             mock.patch.object(ChatService, "_get_config", return_value=object()), \
             mock.patch("services.chat_service.AIService") as ai:
            ai.return_value.generate_content.return_value = "直连回答"
            done = dict(self.service.stream_turn(self.conversation, "沙箱"))["done"]
        self.assertEqual(done["metadata"]["rag_sources"], self.sources)
        with mock.patch.object(ChatService, "_try_hermes_then_compat", return_value=iter(())), \
             mock.patch("services.rag_service.retrieve_context") as retrieve:
            done = dict(self.service.stream_turn(self.conversation, "沙箱"))["done"]
        retrieve.assert_not_called()
        self.assertNotIn("rag_sources", done["metadata"])
