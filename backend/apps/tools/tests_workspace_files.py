from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.agents.models import AgentRun
from apps.projects.models import Conversation
from apps.tools import registry
from apps.tools.handlers import workspace_files
from apps.tools.models import ToolExecution, WorkspaceWrite


@override_settings()
class WorkspaceFilesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="workspace-files")
        self.tempdir = self.enterContext(__import__("tempfile").TemporaryDirectory())
        self.override = override_settings(WORKSPACE_ROOT=self.tempdir)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.handler = mock.Mock(return_value={"ok": True})
        patcher = mock.patch("apps.tools.registry.get_handler", return_value=workspace_files.handle)
        patcher.start()
        self.addCleanup(patcher.stop)

    def approve_once(self, arguments):
        """Run a write through the real approval gate; approve on the SSE event."""
        self.conversation = Conversation.objects.create(user=self.user, tool_approval_required=True)
        self.run = AgentRun.objects.create(user=self.user, conversation=self.conversation,
                                           status="running", task="test")
        context = {"user": self.user, "user_id": self.user.pk,
                   "conversation_id": self.conversation.pk, "run_id": self.run.pk}

        def on_event(kind, data):
            self.assertEqual(kind, "tool_approval")
            ToolExecution.objects.filter(pk=data["id"]).update(status="approved", decision="allow")

        context["on_event"] = on_event
        return registry.execute_tool("workspace_files", arguments, context)

    def test_read_list_write_uncontrolled(self):
        context = {"user": self.user}
        result = registry.execute_tool(
            "workspace_files", {"action": "write", "path": "notes/规划.md", "content": "hello"}, context)
        self.assertTrue(result["ok"], result)
        listing = registry.execute_tool("workspace_files", {"action": "list", "path": ""}, context)
        self.assertTrue(listing["ok"], listing)
        self.assertEqual(listing["result"]["entries"], [{"name": "notes", "type": "dir", "size": None}])
        read = registry.execute_tool("workspace_files", {"action": "read", "path": "notes/规划.md"}, context)
        self.assertTrue(read["ok"])
        self.assertEqual(read["result"]["content"], "hello")
        self.assertFalse(WorkspaceWrite.objects.exists())

    def test_traversal_rejected(self):
        for path in ["../escape.md", "..\\escape.md", "a/../../escape.md"]:
            with self.subTest(path=path):
                result = registry.execute_tool("workspace_files", {"action": "read", "path": path}, {})
                self.assertFalse(result["ok"])

    def test_requires_authenticated_context(self):
        result = registry.execute_tool("workspace_files", {"action": "read", "path": "x.md"}, {})
        self.assertFalse(result["ok"])

    def test_write_over_size_limit(self):
        result = registry.execute_tool(
            "workspace_files", {"action": "write", "path": "big.md", "content": "x" * 60001}, {})
        self.assertFalse(result["ok"])

    def test_controlled_write_requires_approval_and_records_version(self):
        arguments = {"action": "write", "path": "notes/new.md", "content": "approved body"}
        result = self.approve_once(arguments)
        self.assertTrue(result["ok"], result)
        version = WorkspaceWrite.objects.get()
        self.assertEqual(version.path, "notes/new.md")
        self.assertIsNone(version.previous)
        self.assertTrue(version.applied)
        self.assertEqual(version.status, "applied")
        self.assertIn("+approved body", result["result"]["diff"])
        execution = ToolExecution.objects.latest("created_at")
        self.assertEqual(execution.status, "succeeded")
        self.assertEqual(execution.tool_name, "workspace_files")
        # 审批后的重入读取走真实 handler，落版本行后的再读取仍应有内容
        read = registry.execute_tool(
            "workspace_files", {"action": "read", "path": "notes/new.md"},
            {"user": self.user, "user_id": self.user.pk})
        self.assertEqual(read["result"]["content"], "approved body")

    def test_controlled_write_denied_writes_nothing(self):
        self.conversation = Conversation.objects.create(user=self.user, tool_approval_required=True)
        self.run = AgentRun.objects.create(user=self.user, conversation=self.conversation,
                                           status="running", task="test")
        context = {"user": self.user, "user_id": self.user.pk,
                   "conversation_id": self.conversation.pk, "run_id": self.run.pk,
                   "on_event": lambda kind, data: ToolExecution.objects.filter(pk=data["id"]).update(
                       status="denied", decision="deny")}
        result = registry.execute_tool(
            "workspace_files", {"action": "write", "path": "denied.md", "content": "nope"}, context)
        self.assertFalse(result["ok"])
        self.assertFalse(WorkspaceWrite.objects.exists())
        self.assertFalse((workspace_files.workspace_root(self.user.pk) / "denied.md").exists())

    def test_rollback_restores_previous_content(self):
        from rest_framework.test import APIRequestFactory
        from apps.tools.approval_views import workspace_write_rollback

        root = workspace_files.workspace_root(self.user.pk)
        target = root / "doc.md"
        registry.execute_tool(
            "workspace_files", {"action": "write", "path": "doc.md", "content": "v1"},
            {"user": self.user, "user_id": self.user.pk})
        result = self.approve_once({"action": "write", "path": "doc.md", "content": "v2"})
        self.assertTrue(result["ok"])
        version = WorkspaceWrite.objects.latest("id")
        self.assertEqual(version.previous, "v1")
        self.assertEqual(target.read_text(encoding="utf-8"), "v2")
        factory = APIRequestFactory()
        request = factory.post(f"/api/workspace-writes/{version.pk}/rollback/")
        from rest_framework.test import force_authenticate

        force_authenticate(request, self.user)
        response = workspace_write_rollback(request, version.pk)
        self.assertEqual(response.status_code, 200, response.data)
        version.refresh_from_db()
        self.assertEqual(version.status, "rolled_back")
        self.assertEqual(target.read_text(encoding="utf-8"), "v1")
