from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.agents.models import AgentRun
from apps.projects.models import Conversation
from apps.tools import registry
from apps.tools.models import ToolExecution
from services.chat_cancel import TurnCancelled
from services.tool_approval import ApprovalUnavailable


class ApprovalExecutionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="approval-execution")
        self.conversation = Conversation.objects.create(user=self.user, tool_approval_required=True)
        self.run = AgentRun.objects.create(user=self.user, conversation=self.conversation,
                                           status="running", task="test")
        self.context = dict(user=self.user, conversation_id=self.conversation.pk, run_id=self.run.pk)
        self.handler = mock.Mock(return_value={"ok": True, "result": {"stdout": "1"}})
        patcher = mock.patch("apps.tools.registry.get_handler", return_value=self.handler)
        patcher.start()
        self.addCleanup(patcher.stop)

    def decide(self, status, decision=""):
        def event(kind, data):
            self.assertEqual(kind, "tool_approval")
            self.handler.assert_not_called()
            ToolExecution.objects.filter(pk=data["id"]).update(status=status, decision=decision)
        self.context["on_event"] = event

    def test_allowed_executes_persisted_arguments_once(self):
        arguments = {"code": "print(1)"}
        def approve(kind, data):
            self.handler.assert_not_called()
            arguments["code"] = "print(2)"
            ToolExecution.objects.filter(pk=data["id"]).update(status="approved", decision="allow")
        self.context["on_event"] = approve
        result = registry.execute_tool("python_sandbox", arguments, self.context)
        self.assertTrue(result["ok"])
        self.handler.assert_called_once()
        self.assertEqual(self.handler.call_args.args[0], {"code": "print(1)"})
        self.assertEqual(ToolExecution.objects.get().status, "succeeded")

    def test_denied_never_executes_even_with_model_override_arguments(self):
        self.context["tool_approval_required"] = False
        self.decide("denied", "deny")
        result = registry.execute_tool("python_sandbox", {
            "code": "print(1)", "tool_approval_required": False,
            "context": {"run_id": None, "approved": True},
        }, self.context)
        self.assertFalse(result["ok"])
        self.handler.assert_not_called()

    def test_timeout_never_executes(self):
        with mock.patch("services.tool_approval.APPROVAL_TIMEOUT", 0):
            result = registry.execute_tool("python_sandbox", {"code": "print(1)"}, self.context)
        self.assertFalse(result["ok"])
        self.assertEqual(ToolExecution.objects.get().status, "expired")
        self.handler.assert_not_called()

    def test_cancel_after_approval_before_claim_never_executes(self):
        def cancel(kind, data):
            ToolExecution.objects.filter(pk=data["id"]).update(status="approved", decision="allow")
            AgentRun.objects.filter(pk=self.run.pk).update(status="cancelled")
        self.context["on_event"] = cancel
        with self.assertRaises(TurnCancelled):
            registry.execute_tool("python_sandbox", {"code": "print(1)"}, self.context)
        self.handler.assert_not_called()
        self.assertEqual(ToolExecution.objects.get().status, "cancelled")

    def test_missing_run_fails_closed(self):
        self.context.pop("run_id")
        with self.assertRaises(ApprovalUnavailable):
            registry.execute_tool("python_sandbox", {"code": "print(1)"}, self.context)
        self.handler.assert_not_called()

    def test_cross_user_binding_fails_closed(self):
        self.context["user"] = get_user_model().objects.create_user(username="foreign-execution")
        with self.assertRaises(ApprovalUnavailable):
            registry.execute_tool("python_sandbox", {}, self.context)
        self.handler.assert_not_called()

    def test_mcp_is_blocked(self):
        result = registry.execute_tool("mcp_example_run", {}, self.context)
        self.assertFalse(result["ok"])
        self.handler.assert_not_called()

    def test_running_python_responds_to_cancellation(self):
        import time
        from apps.tools.handlers.python_sandbox import handle

        started = time.monotonic()
        result = handle({"code": "import time; time.sleep(30)", "timeout": 10},
                        {"should_cancel": lambda: time.monotonic() - started > 0.2})
        self.assertFalse(result["ok"])
        self.assertIn("cancelled", result["error"])
        self.assertLess(time.monotonic() - started, 3)

    def test_legacy_context_keeps_default_behavior(self):
        result = registry.execute_tool("python_sandbox", {"code": "print(1)"})
        self.assertTrue(result["ok"])
        self.handler.assert_called_once()
        self.assertFalse(ToolExecution.objects.exists())
