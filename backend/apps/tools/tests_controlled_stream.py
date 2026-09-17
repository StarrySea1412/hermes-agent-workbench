import threading
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.agents.models import AgentRun
from apps.projects.models import Conversation
from apps.tools import registry
from apps.tools.models import ToolExecution
from services.chat_service import ChatService


class ControlledStreamTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="controlled-stream")
        self.conversation = Conversation.objects.create(user=self.user, tool_approval_required=True)
        self.run = AgentRun.objects.create(user=self.user, conversation=self.conversation,
                                           status="running", task="test")
        self.service = ChatService(self.user)
        for method, value in [("_build_file_prompt", ""), ("_build_retrieval_prompt", ("", [])),
                              ("_build_memory_prompt", ""), ("_get_runtime_model_name", "test"),
                              ("_get_runtime_base_url", "")]:
            patcher = mock.patch.object(self.service, method, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.handler = mock.Mock(return_value={"ok": True})
        self.finished = threading.Event()

    def loop(self, **kwargs):
        try:
            registry.execute_tool("python_sandbox", {"code": "print(1)"}, kwargs["tool_context"])
            return SimpleNamespace(reply="finished", used_tools=["python_sandbox"])
        finally:
            self.finished.set()

    def stream(self):
        return self.service._stream_controlled_turn(object(), self.conversation, [], [], "test",
                                                   ["python_sandbox"], [], [], [], self.run)

    def test_real_wait_approval_then_completion(self):
        with mock.patch("services.chat_service.run_tool_loop", side_effect=self.loop), \
             mock.patch("apps.tools.registry.get_handler", return_value=self.handler), \
             mock.patch("services.mcp_client.get_user_mcp_tools") as mcp:
            stream = self.stream()
            event, data = next(stream)
            self.assertEqual(event, "tool_approval")
            self.handler.assert_not_called()
            ToolExecution.objects.filter(pk=data["id"]).update(status="approved", decision="allow")
            events = list(stream)
            self.assertEqual(events[-1][0], "done")
            self.handler.assert_called_once()
            mcp.assert_not_called()
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "done")
        self.assertEqual(ToolExecution.objects.get().status, "succeeded")

    def test_disconnect_cancels_waiter_without_execution(self):
        with mock.patch("services.chat_service.run_tool_loop", side_effect=self.loop), \
             mock.patch("apps.tools.registry.get_handler", return_value=self.handler):
            stream = self.stream()
            self.assertEqual(next(stream)[0], "tool_approval")
            stream.close()
            self.assertTrue(self.finished.wait(3), "approval worker did not stop")
            self.handler.assert_not_called()
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "cancelled")
        self.assertEqual(ToolExecution.objects.get().status, "cancelled")

    def test_worker_failure_marks_run_failed(self):
        with mock.patch("services.chat_service.run_tool_loop", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                list(self.stream())
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "failed")
