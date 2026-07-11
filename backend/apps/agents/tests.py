import shutil
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient, APITestCase

from apps.agents.models import Agent, AgentArtifact, AgentMemory, AgentRun, AgentStep, MultiAgentWorkflow
from apps.agents.skill_loader import get_skill_details, list_skills, load_skill_text, skill_exists
from apps.agents.workflows import create_bid_workflow
from apps.bids.models import Bid, BidChapter, BidStep
from apps.files.models import UploadedFile
from apps.tools.handlers import doc_export, web_search
from apps.users.authentication import create_access_token
from apps.users.models import User
from services.hermes_service import HermesService


class SkillLoaderTests(SimpleTestCase):
    def test_project_skill_can_be_loaded_from_repo_root(self):
        self.assertTrue(skill_exists("bid-writing/bid-chapter-writer"))
        text = load_skill_text("bid-writing/bid-chapter-writer")
        self.assertIsNotNone(text)
        self.assertIn("Bid Chapter Writer", text)

    def test_generic_agent_engineering_skills_are_available(self):
        self.assertTrue(skill_exists("agent-engineering/general-operator"))
        self.assertTrue(skill_exists("agent-engineering/research-scout"))
        self.assertTrue(skill_exists("agent-engineering/artifact-builder"))

    def test_skill_listing_returns_metadata(self):
        details = get_skill_details("bid-writing/bid-chapter-writer")
        self.assertIsNotNone(details)
        self.assertEqual(details["path"], "bid-writing/bid-chapter-writer")
        self.assertTrue(any(skill["path"] == details["path"] for skill in list_skills()))


class HermesServiceTests(SimpleTestCase):
    @patch("services.hermes_service.OpenAI")
    def test_generate_chapter_passes_system_prompt(self, mock_openai):
        mock_openai.return_value = MagicMock()
        service = HermesService(session_id="session-1")
        service.chat = MagicMock(return_value="done")

        service.generate_chapter(
            chapter_title="Overview",
            prompt="Focus on delivery",
            system_prompt="skill prompt",
        )

        service.chat.assert_called_once()
        self.assertEqual(service.chat.call_args.kwargs["system_prompt"], "skill prompt")


class ToolHandlerTests(SimpleTestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_web_search_returns_clear_error_without_provider(self):
        result = web_search.handle({"query": "hermes agent workbench"})

        self.assertFalse(result["ok"])
        self.assertIn("No web search provider is configured", result["error"])


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY="test-jwt-secret-key-with-32-bytes!!",
)
class BidWorkflowBlueprintTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="workflow-owner", password="password123")
        self.bid = Bid.objects.create(
            title="City Data Platform Bid",
            user=self.user,
            status="draft",
            completed_chapters=0,
            total_chapters=2,
        )
        self.chapter_a = BidChapter.objects.create(bid=self.bid, title="Executive Summary", order=0)
        self.chapter_a_child = BidChapter.objects.create(
            bid=self.bid,
            parent=self.chapter_a,
            title="Executive Summary Appendix",
            order=1,
        )
        self.chapter_b = BidChapter.objects.create(bid=self.bid, title="Implementation Plan", order=2)
        BidStep.objects.create(bid=self.bid, order=0, label="Analyze", status="completed")
        BidStep.objects.create(bid=self.bid, order=1, label="Draft", status="pending")

    def test_create_bid_workflow_creates_default_blueprint(self):
        workflow = create_bid_workflow(
            bid=self.bid,
            user=self.user,
            objective="Prepare a compliant multi-agent draft",
        )
        workflow.refresh_from_db()

        self.assertEqual(MultiAgentWorkflow.objects.count(), 1)
        self.assertEqual(
            Agent.objects.filter(
                slug__in=[
                    "tender-analyzer",
                    "chapter-planner",
                    "chapter-writer",
                    "compliance-reviewer",
                ]
            ).count(),
            4,
        )
        self.assertEqual(workflow.objective, "Prepare a compliant multi-agent draft")
        self.assertEqual(workflow.node_count, 5)
        self.assertEqual(workflow.metadata["chapter_count"], 2)
        self.assertFalse(workflow.metadata["include_child_chapters"])

        self.assertEqual(
            list(workflow.nodes.order_by("order").values_list("key", flat=True)),
            [
                "analyzer",
                "planner",
                f"writer-{self.chapter_a.id}",
                f"writer-{self.chapter_b.id}",
                "reviewer",
            ],
        )

        reviewer = workflow.nodes.get(key="reviewer")
        self.assertEqual(reviewer.depends_on, [f"writer-{self.chapter_a.id}", f"writer-{self.chapter_b.id}"])

        writer_node = workflow.nodes.get(key=f"writer-{self.chapter_a.id}")
        self.assertEqual(writer_node.metadata["chapter_title"], "Executive Summary")
        self.assertEqual(writer_node.input_artifacts, ["bid_snapshot", "chapter_plan", "requirements_report"])

        self.assertCountEqual(
            workflow.artifacts.values_list("key", flat=True),
            ["bid_snapshot", "reference_files"],
        )
        snapshot = workflow.artifacts.get(key="bid_snapshot")
        self.assertEqual(
            [chapter["id"] for chapter in snapshot.payload["chapters"]],
            [self.chapter_a.id, self.chapter_b.id],
        )

    def test_create_bid_workflow_can_include_child_chapters(self):
        workflow = create_bid_workflow(
            bid=self.bid,
            user=self.user,
            include_child_chapters=True,
        )
        workflow.refresh_from_db()

        self.assertEqual(workflow.node_count, 6)
        self.assertEqual(workflow.metadata["chapter_count"], 3)
        self.assertTrue(workflow.metadata["include_child_chapters"])
        self.assertTrue(workflow.nodes.filter(key=f"writer-{self.chapter_a_child.id}").exists())


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY="test-jwt-secret-key-with-32-bytes!!",
)
class MultiAgentWorkflowApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bid-user", password="password123")
        self.other_user = User.objects.create_user(username="other-user", password="password123")
        self.client = self._make_client(self.user)
        self.other_client = self._make_client(self.other_user)
        self.bid = Bid.objects.create(title="Metro Operations Bid", user=self.user, total_chapters=1)
        self.chapter = BidChapter.objects.create(bid=self.bid, title="Delivery Plan", order=0)
        BidStep.objects.create(bid=self.bid, order=0, label="Analyze", status="completed")

    def _make_client(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user.id)}")
        return client

    def test_create_multi_agent_workflow_returns_detail_payload(self):
        response = self.client.post(
            f"/api/bids/{self.bid.id}/multi-agent/workflows",
            {"objective": "Draft and review this bid"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(MultiAgentWorkflow.objects.count(), 1)
        self.assertEqual(response.data["kind"], "bid_pipeline")
        self.assertEqual(response.data["objective"], "Draft and review this bid")
        self.assertEqual(response.data["node_count"], 4)
        self.assertEqual(len(response.data["nodes"]), 4)
        self.assertCountEqual(
            [node["key"] for node in response.data["nodes"]],
            ["analyzer", "planner", f"writer-{self.chapter.id}", "reviewer"],
        )
        self.assertCountEqual(
            [artifact["key"] for artifact in response.data["artifacts"]],
            ["bid_snapshot", "reference_files"],
        )

    def test_workflow_endpoints_are_scoped_to_bid_owner(self):
        workflow = create_bid_workflow(bid=self.bid, user=self.user)

        list_response = self.client.get(f"/api/bids/{self.bid.id}/multi-agent/workflows")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["id"], workflow.id)

        detail_response = self.client.get(f"/api/bids/{self.bid.id}/multi-agent/workflows/{workflow.id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["id"], workflow.id)

        other_list_response = self.other_client.get(f"/api/bids/{self.bid.id}/multi-agent/workflows")
        self.assertEqual(other_list_response.status_code, 404)

        other_detail_response = self.other_client.get(f"/api/bids/{self.bid.id}/multi-agent/workflows/{workflow.id}")
        self.assertEqual(other_detail_response.status_code, 404)

    def test_execute_workflow_runs_nodes_and_persists_outputs(self):
        workflow = create_bid_workflow(bid=self.bid, user=self.user)

        class DummyHermes:
            def __init__(self, *args, **kwargs):
                self.session_id = kwargs.get("session_id")

            def health_check(self):
                return {"connected": True}

        def fake_run_loop(run, _hermes, max_steps=None):
            del max_steps
            if run.agent and run.agent.slug == "tender-analyzer":
                answer = "## Requirements\n- Provide the delivery plan.\n- Show implementation risks."
            elif run.agent and run.agent.slug == "chapter-planner":
                answer = "## Chapter Plan\n- Delivery Plan: address scope, schedule, and controls."
            elif run.agent and run.agent.slug == "chapter-writer":
                answer = "# Delivery Plan\n\nWe will deliver the work in phased milestones."
            else:
                answer = "## Review Report\n- Draft is aligned with the requirements."

            AgentStep.objects.create(
                run=run,
                order=1,
                type="answer",
                status="ok",
                content={"answer": answer},
            )
            run.update_status_atomic(
                "done",
                answer=answer,
                completed_at=timezone.now(),
                step_count=1,
                tools_used=[],
            )
            run.refresh_from_db()
            yield {"order": 1, "type": "answer", "status": "ok", "content": {"answer": answer}}

        with patch("apps.agents.views.HermesService", DummyHermes), patch(
            "apps.agents.workflows.executor.HermesService",
            DummyHermes,
        ), patch("apps.agents.workflows.executor.run_agent_loop", side_effect=fake_run_loop):
            response = self.client.post(
                f"/api/bids/{self.bid.id}/multi-agent/workflows/{workflow.id}/execute",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "done")
        self.assertEqual(response.data["completed_nodes"], 4)
        self.assertTrue(all(node["status"] == "done" for node in response.data["nodes"]))
        self.assertTrue(all(node["agent_run_id"] for node in response.data["nodes"]))
        self.assertCountEqual(
            [artifact["key"] for artifact in response.data["artifacts"]],
            [
                "bid_snapshot",
                "reference_files",
                "requirements_report",
                "chapter_plan",
                f"chapter-draft-{self.chapter.id}",
                "review_report",
            ],
        )

        self.bid.refresh_from_db()
        self.chapter.refresh_from_db()
        self.assertEqual(self.bid.status, "active")
        self.assertEqual(self.bid.completed_chapters, 1)
        self.assertTrue(self.chapter.content)

    def test_cancel_workflow_cancels_active_agent_run(self):
        workflow = create_bid_workflow(bid=self.bid, user=self.user)
        running_node = workflow.nodes.order_by("order").first()
        agent_run = AgentRun.objects.create(
            user=self.user,
            agent=running_node.agent,
            task="In-flight node run",
            status="running",
            max_steps=4,
            session_id=f"u{self.user.id}-wf{workflow.id}-{running_node.key}",
            started_at=timezone.now(),
        )
        workflow.status = "running"
        workflow.current_node_key = running_node.key
        workflow.started_at = timezone.now()
        workflow.save(update_fields=["status", "current_node_key", "started_at", "updated_at"])
        running_node.status = "running"
        running_node.agent_run = agent_run
        running_node.started_at = timezone.now()
        running_node.save(update_fields=["status", "agent_run", "started_at", "updated_at"])

        response = self.client.post(
            f"/api/bids/{self.bid.id}/multi-agent/workflows/{workflow.id}/cancel",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")
        running_node.refresh_from_db()
        agent_run.refresh_from_db()
        self.assertEqual(running_node.status, "cancelled")
        self.assertEqual(agent_run.status, "cancelled")


@override_settings(
    LOCAL_SINGLE_USER_MODE=False,
    JWT_SECRET_KEY="test-jwt-secret-key-with-32-bytes!!",
)
class AgentRunApiTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.user = User.objects.create_user(username="agent-user", password="password123")
        self.other_user = User.objects.create_user(username="agent-other", password="password123")
        self.client = self._make_client(self.user)
        self.other_client = self._make_client(self.other_user)

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def _make_client(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user.id)}")
        return client

    def test_agent_templates_endpoint_seeds_default_catalog(self):
        response = self.client.get("/api/agent-templates")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 3)
        self.assertTrue(any(item["slug"] == "general-operator" for item in response.data))
        self.assertTrue(any(item["skill"] == "agent-engineering/general-operator" for item in response.data))

    def test_agent_template_crud(self):
        create_response = self.client.post(
            "/api/agent-templates/create",
            {
                "name": "Repository Analyst",
                "slug": "repository-analyst",
                "skill": "agent-engineering/research-scout",
                "system_prompt": "Inspect repositories and summarize runtime behavior.",
                "default_max_steps": 7,
                "allowed_tools": ["doc_parse", "web_search"],
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        agent_id = create_response.data["id"]
        self.assertEqual(create_response.data["slug"], "repository-analyst")
        self.assertEqual(create_response.data["allowed_tools"], ["doc_parse", "web_search"])

        detail_response = self.client.get(f"/api/agent-templates/{agent_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["name"], "Repository Analyst")

        patch_response = self.client.patch(
            f"/api/agent-templates/{agent_id}",
            {"default_max_steps": 9, "system_prompt": "Inspect codebases and emit engineering notes."},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data["default_max_steps"], 9)

        delete_response = self.client.delete(f"/api/agent-templates/{agent_id}")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Agent.objects.filter(id=agent_id).exists())

    def test_tools_endpoint_returns_registry(self):
        response = self.client.get("/api/tools")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["name"] == "doc_parse" for item in response.data))
        web_search = next(item for item in response.data if item["name"] == "web_search")
        self.assertTrue(web_search["registered"])
        self.assertEqual(web_search["runtime"], "network")

    def test_memory_crud_and_run_attachment(self):
        create_memory = self.client.post(
            "/api/memories",
            {
                "title": "Workspace preferences",
                "content": "Prefer concise technical summaries and explicit assumptions.",
                "scope": "workspace",
                "tags": ["style", "summary"],
                "pinned": True,
            },
            format="json",
        )
        self.assertEqual(create_memory.status_code, 201)
        memory_id = create_memory.data["id"]

        list_response = self.client.get("/api/memories?scope=workspace&pinned=true")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(list_response.data[0]["id"], memory_id)

        patch_response = self.client.patch(
            f"/api/memories/{memory_id}",
            {"pinned": False, "tags": ["style"]},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertFalse(patch_response.data["pinned"])

        run_response = self.client.post(
            "/api/agent-runs",
            {
                "task": "Summarize repository runtime behavior.",
                "memory_ids": [memory_id],
            },
            format="json",
        )
        self.assertEqual(run_response.status_code, 201)
        run_id = run_response.data["id"]
        self.assertEqual(run_response.data["memory_ids"], [memory_id])

        run_memories = self.client.get(f"/api/agent-runs/{run_id}/memories")
        self.assertEqual(run_memories.status_code, 200)
        self.assertEqual([item["id"] for item in run_memories.data], [memory_id])

        other_detail = self.other_client.get(f"/api/memories/{memory_id}")
        self.assertEqual(other_detail.status_code, 404)

    def test_create_and_fetch_agent_run(self):
        agent = Agent.objects.create(
            name="Test Operator",
            slug="test-operator",
            skill="agent-engineering/general-operator",
            system_prompt="Handle engineering tasks.",
            default_max_steps=6,
            allowed_tools=["doc_parse"],
        )
        memory = AgentMemory.objects.create(
            user=self.user,
            title="API conventions",
            content="Prefer structured JSON examples.",
            scope="user",
        )

        create_response = self.client.post(
            "/api/agent-runs",
            {
                "task": "Inspect the repository and summarize the runtime shape.",
                "agent_id": agent.id,
                "max_steps": 5,
                "memory_ids": [memory.id],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        run_id = create_response.data["id"]
        self.assertEqual(create_response.data["status"], "pending")
        self.assertEqual(create_response.data["max_steps"], 5)
        self.assertEqual(create_response.data["agent"]["slug"], "test-operator")
        self.assertEqual(create_response.data["memory_ids"], [memory.id])

        detail_response = self.client.get(f"/api/agent-runs/{run_id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["id"], run_id)
        self.assertEqual(detail_response.data["task"], "Inspect the repository and summarize the runtime shape.")
        self.assertEqual(len(detail_response.data["memories"]), 1)
        self.assertEqual(detail_response.data["memories"][0]["id"], memory.id)

        other_detail = self.other_client.get(f"/api/agent-runs/{run_id}")
        self.assertEqual(other_detail.status_code, 404)

    def test_create_and_fetch_agent_run_with_attached_files(self):
        agent = Agent.objects.create(
            name="File Operator",
            slug="file-operator",
            skill="agent-engineering/research-scout",
            system_prompt="Use attached files during analysis.",
            default_max_steps=6,
            allowed_tools=["doc_parse"],
        )
        uploaded = UploadedFile.objects.create(
            user=self.user,
            file=SimpleUploadedFile("architecture.md", b"# Runtime\nAttached context", content_type="text/markdown"),
            original_name="architecture.md",
            file_type="md",
            file_size=26,
            description="System architecture notes.",
        )

        create_response = self.client.post(
            "/api/agent-runs",
            {
                "task": "Review the attached architecture notes.",
                "agent_id": agent.id,
                "file_ids": [uploaded.id],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.data["file_ids"], [uploaded.id])
        self.assertEqual(len(create_response.data["files"]), 1)
        self.assertEqual(create_response.data["files"][0]["id"], uploaded.id)
        self.assertEqual(create_response.data["files"][0]["original_name"], "architecture.md")

        detail_response = self.client.get(f"/api/agent-runs/{create_response.data['id']}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["file_ids"], [uploaded.id])
        self.assertEqual(len(detail_response.data["files"]), 1)
        self.assertTrue(detail_response.data["files"][0]["file_url"].startswith("http://testserver/"))

    def test_create_agent_run_rejects_foreign_file_ids(self):
        foreign_file = UploadedFile.objects.create(
            user=self.other_user,
            file=SimpleUploadedFile("other-notes.txt", b"private", content_type="text/plain"),
            original_name="other-notes.txt",
            file_type="txt",
            file_size=7,
        )

        response = self.client.post(
            "/api/agent-runs",
            {
                "task": "Attempt to attach another user's file.",
                "file_ids": [foreign_file.id],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("file_ids", response.data)

    @patch("apps.agents.views.run_agent_loop")
    @patch("apps.agents.views.HermesService")
    def test_execute_agent_run_stream_returns_events_and_persists_run(self, mock_hermes_cls, mock_run_loop):
        agent = Agent.objects.create(
            name="Stream Operator",
            slug="stream-operator",
            skill="agent-engineering/general-operator",
            system_prompt="Stream execution events.",
            default_max_steps=4,
        )
        run = AgentRun.objects.create(
            user=self.user,
            agent=agent,
            task="Run a streaming execution test.",
            status="pending",
            max_steps=4,
            session_id="u1-run1",
        )

        hermes_instance = MagicMock()
        hermes_instance.health_check.return_value = {"connected": True}
        mock_hermes_cls.return_value = hermes_instance

        def fake_run_loop(current_run, hermes, max_steps=None):
            self.assertEqual(current_run.id, run.id)
            self.assertEqual(max_steps, 4)

            step = AgentStep.objects.create(
                run=current_run,
                order=1,
                type="plan",
                status="ok",
                thought="Planning the mocked run.",
                content={"task": current_run.task},
            )
            current_run.status = "done"
            current_run.answer = "Mocked final answer"
            current_run.step_count = 1
            current_run.tools_used = ["web_search"]
            current_run.save(update_fields=["status", "answer", "step_count", "tools_used", "updated_at"])
            yield {
                "step_id": step.id,
                "order": 1,
                "type": "plan",
                "status": "ok",
                "thought": "Planning the mocked run.",
                "content": {"task": current_run.task},
            }

        mock_run_loop.side_effect = fake_run_loop

        response = self.client.post(f"/api/agent-runs/{run.id}/execute-stream")

        self.assertEqual(response.status_code, 200)
        payload = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("event: run", payload)
        self.assertIn("event: step", payload)
        self.assertIn("event: complete", payload)
        self.assertIn("Mocked final answer", payload)

        run.refresh_from_db()
        self.assertEqual(run.status, "done")
        self.assertEqual(run.answer, "Mocked final answer")
        self.assertEqual(run.step_count, 1)

    def test_agent_run_artifacts_endpoint_returns_persisted_artifacts(self):
        agent = Agent.objects.create(
            name="Artifact Operator",
            slug="artifact-operator",
            skill="agent-engineering/artifact-builder",
            system_prompt="Create trace artifacts.",
            default_max_steps=4,
        )
        run = AgentRun.objects.create(
            user=self.user,
            agent=agent,
            task="Collect artifacts for inspection.",
            status="done",
            max_steps=4,
            session_id="u3-run-artifacts",
            answer="Final artifact answer",
            tools_used=["web_search"],
            step_count=3,
        )
        artifact = AgentArtifact.objects.create(
            user=self.user,
            run=run,
            key="final-answer",
            title="Final answer",
            artifact_type="answer",
            source="agent",
            payload={"answer": run.answer},
            metadata={"step_count": run.step_count},
        )

        response = self.client.get(f"/api/agent-runs/{run.id}/artifacts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], artifact.id)
        self.assertEqual(response.data[0]["artifact_type"], "answer")

    def test_cancel_pending_agent_run(self):
        run = AgentRun.objects.create(
            user=self.user,
            task="Cancel this queued run.",
            status="pending",
            max_steps=4,
            session_id="u1-run-cancel",
        )

        response = self.client.post(f"/api/agent-runs/{run.id}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")

        run.refresh_from_db()
        self.assertEqual(run.status, "cancelled")
        self.assertIsNotNone(run.completed_at)

    def test_cannot_cancel_completed_run(self):
        run = AgentRun.objects.create(
            user=self.user,
            task="Already done.",
            status="done",
            max_steps=4,
            session_id="u1-run-done",
        )

        response = self.client.post(f"/api/agent-runs/{run.id}/cancel")

        self.assertEqual(response.status_code, 409)

    def test_agent_run_save_memory_promotes_final_answer(self):
        run = AgentRun.objects.create(
            user=self.user,
            task="Summarize the current system behavior.",
            status="done",
            max_steps=4,
            answer="The system exposes runs, templates, and persistent artifacts.",
            session_id="u5-run-memory",
        )

        response = self.client.post(
            f"/api/agent-runs/{run.id}/save-memory",
            {
                "title": "Runtime summary",
                "scope": "workspace",
                "tags": ["runtime", "summary"],
                "pinned": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(AgentMemory.objects.count(), 1)
        memory = AgentMemory.objects.get()
        self.assertEqual(memory.run_id, run.id)
        self.assertEqual(memory.title, "Runtime summary")
        self.assertTrue(memory.pinned)
        self.assertIn("persistent artifacts", memory.content)

    def test_doc_export_persists_generated_markdown_file(self):
        result = doc_export.handle(
            {
                "content": "# Spec\nGenerated artifact",
                "format": "markdown",
                "title": "agent-spec",
            },
            {"user": self.user},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(UploadedFile.objects.count(), 1)
        uploaded = UploadedFile.objects.get()
        self.assertEqual(uploaded.original_name, "agent-spec.md")
        self.assertEqual(uploaded.file_type, "md")
        self.assertGreater(uploaded.file_size, 0)
        self.assertTrue(uploaded.file.name.endswith("agent-spec.md"))
        self.assertTrue(result["result"]["url"].endswith("agent-spec.md"))

    def test_doc_export_persists_generated_xlsx_file(self):
        result = doc_export.handle(
            {
                "format": "xlsx",
                "title": "world-cup-odds",
                "sheet_name": "Odds",
                "columns": ["Team", "Odds"],
                "rows": [
                    ["Brazil", 4.5],
                    ["France", "5.25"],
                ],
            },
            {"user": self.user},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(UploadedFile.objects.count(), 1)
        uploaded = UploadedFile.objects.get()
        self.assertEqual(uploaded.original_name, "world-cup-odds.xlsx")
        self.assertEqual(uploaded.file_type, "xlsx")
        self.assertGreater(uploaded.file_size, 0)
        self.assertEqual(result["result"]["format"], "xlsx")
        self.assertTrue(result["result"]["url"].endswith("world-cup-odds.xlsx"))

        with uploaded.file.open("rb") as file_obj:
            with zipfile.ZipFile(file_obj) as archive:
                names = set(archive.namelist())
                self.assertIn("[Content_Types].xml", names)
                self.assertIn("xl/workbook.xml", names)
                self.assertIn("xl/worksheets/sheet1.xml", names)
                worksheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                workbook = archive.read("xl/workbook.xml").decode("utf-8")

        self.assertIn('name="Odds"', workbook)
        self.assertIn("Brazil", worksheet)
        self.assertIn("<v>4.5</v>", worksheet)
