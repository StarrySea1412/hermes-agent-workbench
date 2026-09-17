"""Regression coverage for the controlled chat dispatch boundary."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from services.chat_service import ChatService


class ControlledDispatchTests(SimpleTestCase):
    def test_successful_controlled_done_does_not_raise_or_fallback(self):
        service = ChatService(SimpleNamespace(id=1))
        conversation = SimpleNamespace(id=1, project_id=None, tool_approval_required=True)
        done = {"reply": "approved result", "metadata": {"approval_mode": True}}

        def completed_turn(*args, **kwargs):
            yield "done", done

        with patch.object(service, "get_session_id", return_value="test-session"), \
             patch.object(service, "get_context_files", return_value=[]), \
             patch.object(service, "get_history", return_value=[]), \
             patch.object(service, "resolve_tool_names", return_value=[]), \
             patch.object(service, "_start_chat_agent_run", return_value=object()), \
             patch.object(service, "_get_compat_agent", return_value=object()), \
             patch.object(service, "_stream_controlled_turn", side_effect=completed_turn), \
             patch("services.chat_service.create_hermes_service") as hermes, \
             patch.object(service, "_fallback_or_ai_reply") as fallback:
            events = list(service.stream_turn(conversation, "hello"))

        self.assertEqual(events, [("done", done)])
        hermes.assert_not_called()
        fallback.assert_not_called()
