"""网关会话取证与聊天取消的回归测试。

覆盖：
1. HermesService.fetch_session_tool_trace 的消息归并逻辑（mock httpx 响应）
2. chat_cancel 注册表的登记/清除语义
3. ChatService._enrich_tool_events 的参数回填与不可信壳剥离
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.projects.models import Conversation
from services.chat_cancel import (
    _reset_cache_for_tests,
    clear_chat_cancel,
    is_chat_cancelled,
    request_chat_cancel,
)
from services.chat_service import ChatService
from services.hermes_service import HermesService


class ChatCancelRegistryTests(TestCase):
    def setUp(self):
        _reset_cache_for_tests()
        self.user = get_user_model().objects.create_user(username="cancel-user", password="x")
        self.conversation = Conversation.objects.create(user=self.user, title="t")

    def tearDown(self):
        _reset_cache_for_tests()

    def test_request_and_clear(self):
        self.assertFalse(is_chat_cancelled(self.conversation.id))
        request_chat_cancel(self.conversation.id)
        self.assertTrue(is_chat_cancelled(self.conversation.id))
        # 标记在 DB 上，跨 worker/进程可见
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.cancel_requested)
        clear_chat_cancel(self.conversation.id)
        self.assertFalse(is_chat_cancelled(self.conversation.id))
        self.conversation.refresh_from_db()
        self.assertFalse(self.conversation.cancel_requested)

    def test_unknown_conversation_defaults_false(self):
        self.assertFalse(is_chat_cancelled(999999))

    def test_request_missing_conversation_returns_false(self):
        self.assertFalse(request_chat_cancel(999999))


def _session_payload():
    return {
        "object": "list",
        "session_id": "u1-p1",
        "data": [
            {"id": 1, "role": "user", "content": "hi", "tool_calls": None},
            {
                "id": 2,
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{\"query\": \"glass ui\"}"},
                }],
            },
            {
                "id": 3,
                "role": "tool",
                "tool_call_id": "call_abc",
                "content": (
                    '<untrusted_tool_result source="web_search">\n'
                    " advisory text\n\n"
                    "{\"success\": true, \"data\": {\"web\": []}}\n"
                    "</untrusted_tool_result>"
                ),
            },
        ],
    }


class FetchSessionToolTraceTests(SimpleTestCase):
    def _fetch(self, payload):
        service = HermesService(session_id="u1-p1")
        response = mock.Mock()
        response.raise_for_status = mock.Mock()
        response.json.return_value = payload
        with mock.patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.return_value = response
            return service.fetch_session_tool_trace()

    def test_merges_calls_and_results_by_call_id(self):
        trace = self._fetch(_session_payload())
        self.assertIn("call_abc", trace)
        record = trace["call_abc"]
        self.assertEqual(record["name"], "web_search")
        self.assertEqual(record["args"], {"query": "glass ui"})
        self.assertIn("untrusted_tool_result", record["result_content"])

    def test_missing_session_returns_empty(self):
        service = HermesService(session_id=None)
        self.assertEqual(service.fetch_session_tool_trace(), {})

    def test_request_error_returns_empty(self):
        service = HermesService(session_id="u1-p1")
        with mock.patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.side_effect = RuntimeError("boom")
            self.assertEqual(service.fetch_session_tool_trace(), {})


class EnrichToolEventsTests(SimpleTestCase):
    def test_backfills_args_and_strips_untrusted_wrapper(self):
        events = [{
            "id": "call_abc",
            "name": "web_search",
            "args": {},
            "thought": "",
            "status": "ok",
            "result_preview": "glass ui",
        }]
        trace = {
            "call_abc": {
                "name": "web_search",
                "args": {"query": "glass ui"},
                "result_content": (
                    '<untrusted_tool_result source="web_search">\n advisory\n\n'
                    "{\"success\": true}\n</untrusted_tool_result>"
                ),
            },
        }
        agent = mock.Mock()
        agent.fetch_session_tool_trace.return_value = trace
        ChatService._enrich_tool_events(mock.Mock(), agent, events)

        event = events[0]
        self.assertEqual(event["args"], {"query": "glass ui"})
        self.assertEqual(event["result"]["ok"], True)
        self.assertIn('{"success": true}', event["result"]["result"])
        self.assertNotIn("untrusted_tool_result", event["result"]["result"])

    def test_events_without_trace_entry_are_untouched(self):
        events = [{"id": "call_other", "name": "web_search", "args": {}, "status": "ok"}]
        agent = mock.Mock()
        agent.fetch_session_tool_trace.return_value = {}
        ChatService._enrich_tool_events(mock.Mock(), agent, events)
        self.assertEqual(events[0]["args"], {})
        self.assertNotIn("result", events[0])
