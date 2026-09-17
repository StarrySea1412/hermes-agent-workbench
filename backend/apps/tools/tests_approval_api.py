from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.agents.models import AgentRun
from apps.projects.models import Conversation
from apps.tools.models import ToolExecution


class ApprovalApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="approval-api-test")
        self.client.force_authenticate(self.user)
        self.conversation = Conversation.objects.create(user=self.user, title="Approval test")
        self.run = AgentRun.objects.create(
            user=self.user, conversation=self.conversation, task="Approval test", status="running")

    def execution(self, **overrides):
        values = dict(user=self.user, conversation=self.conversation, run=self.run,
                      tool_name="python_sandbox", arguments={"code": "print(1)"},
                      expires_at=timezone.now() + timedelta(seconds=120))
        values.update(overrides)
        return ToolExecution.objects.create(**values)

    def allow(self, execution):
        return self.client.post(f"/api/tool-executions/{execution.pk}/decision/",
                                {"decision": "allow"}, format="json")

    def test_create_preserves_explicit_approval_mode(self):
        response = self.client.post("/api/conversations/", {
            "title": "Controlled", "tool_approval_required": True,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["tool_approval_required"])

    def test_other_user_cannot_read_or_decide(self):
        execution = self.execution()
        other = get_user_model().objects.create_user(username="other-approval-user")
        self.client.force_authenticate(other)
        self.assertEqual(self.allow(execution).status_code, 404)
        response = self.client.get("/api/tool-executions/", {"conversation_id": self.conversation.pk})
        self.assertEqual(response.status_code, 404)
        execution.refresh_from_db()
        self.assertEqual(execution.status, "pending")

    def test_run_cancelled_after_allow_cannot_be_approved_again(self):
        execution = self.execution()
        self.assertEqual(self.allow(execution).status_code, 200)
        self.run.status = "cancelled"
        self.run.save(update_fields=["status"])
        self.assertEqual(self.allow(execution).status_code, 409)
        execution.refresh_from_db()
        self.assertEqual(execution.status, "cancelled")

    def test_opposite_decision_conflicts(self):
        execution = self.execution()
        self.assertEqual(self.allow(execution).status_code, 200)
        response = self.client.post(f"/api/tool-executions/{execution.pk}/decision/",
                                    {"decision": "deny"}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_patch_approval_required(self):
        self.assertFalse(self.conversation.tool_approval_required)
        response = self.client.patch(f"/api/conversations/{self.conversation.pk}/",
                                     {"tool_approval_required": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["tool_approval_required"])
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.tool_approval_required)

    def test_duplicate_allow_is_200(self):
        execution = self.execution()
        first = self.allow(execution)
        self.assertEqual(first.status_code, 200, first.data)
        second = self.allow(execution)
        self.assertEqual(second.status_code, 200, second.data)
        execution.refresh_from_db()
        self.assertEqual(execution.status, "approved")
        self.assertIsNone(execution.result)

    def test_cancelled_allow_is_409(self):
        execution = self.execution(status="cancelled", decision="allow")
        response = self.allow(execution)
        self.assertEqual(response.status_code, 409, response.data)
        execution.refresh_from_db()
        self.assertEqual(execution.status, "cancelled")

    def test_expired_allow_is_409(self):
        execution = self.execution(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.allow(execution)
        self.assertEqual(response.status_code, 409, response.data)
        execution.refresh_from_db()
        self.assertEqual(execution.status, "expired")
