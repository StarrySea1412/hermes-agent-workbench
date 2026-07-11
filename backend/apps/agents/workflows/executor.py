import json

from django.utils import timezone

from apps.agents.models import AgentRun, MultiAgentWorkflow, WorkflowArtifact
from apps.agents.orchestrator import DEFAULT_MAX_STEPS, ensure_run_mission_artifact, run_agent_loop
from apps.bids.models import BidChapter
from services.hermes_service import HermesService
from services.text_utils import text_to_canvas_format

WORKFLOW_CANCELLED_NOTICE = "Workflow cancelled by user."


def _stringify_payload(payload, max_chars=2400):
    if payload is None:
        return "No payload."
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


def _workflow_is_cancelled(workflow: MultiAgentWorkflow):
    workflow.refresh_from_db(fields=["status", "completed_at", "updated_at", "current_node_key", "completed_nodes"])
    return workflow.status == "cancelled"


def _reference_file_ids(workflow: MultiAgentWorkflow):
    artifact = workflow.artifacts.filter(key="reference_files").first()
    files = ((artifact.payload or {}).get("files") or []) if artifact else []
    ids = []
    seen = set()
    for item in files:
        try:
            file_id = int((item or {}).get("id"))
        except (TypeError, ValueError):
            continue
        if file_id <= 0 or file_id in seen:
            continue
        seen.add(file_id)
        ids.append(file_id)
    return ids


def _format_node_instruction(node):
    if node.node_type == "analysis":
        return (
            "Analyze the source material and extract requirements, constraints, deliverables, scoring criteria, "
            "risks, and open questions. Return a structured Markdown report."
        )
    if node.node_type == "planning":
        return (
            "Turn the available requirements into an execution and writing plan. Organize the response as a chapter "
            "strategy with priorities, evidence needs, and drafting guidance."
        )
    if node.node_type == "writing":
        chapter_title = (node.metadata or {}).get("chapter_title") or (node.chapter.title if node.chapter_id and node.chapter else "Untitled chapter")
        return (
            f"Draft the chapter '{chapter_title}' in polished Markdown. Write the actual deliverable content, "
            "not a meta-plan. Use headings, lists, and explicit assumptions where needed."
        )
    if node.node_type == "review":
        return (
            "Review the drafted materials for compliance, consistency, missing evidence, and revision priorities. "
            "Return a structured review report with findings and recommended fixes."
        )
    return "Complete the node objective and return a useful Markdown artifact."


def _build_node_task(workflow: MultiAgentWorkflow, node, artifact_map):
    sections = [
        f"Workflow title: {workflow.title or f'Workflow {workflow.id}'}",
        f"Workflow objective: {workflow.objective or 'No objective provided.'}",
        f"Current node: {node.label}",
        f"Node type: {node.node_type}",
        f"Node instruction: {_format_node_instruction(node)}",
    ]

    if node.chapter_id:
        chapter_title = (node.metadata or {}).get("chapter_title") or (node.chapter.title if node.chapter_id and node.chapter else "")
        if chapter_title:
            sections.append(f"Target chapter: {chapter_title}")

    artifact_sections = []
    for key in node.input_artifacts or []:
        artifact = artifact_map.get(key)
        if not artifact:
            artifact_sections.append(f"Artifact '{key}' is unavailable.")
            continue
        artifact_sections.append(
            f"Artifact: {key}\nTitle: {artifact.title or key}\nPayload:\n{_stringify_payload(artifact.payload)}"
        )

    if artifact_sections:
        sections.append("Available workflow artifacts:\n\n" + "\n\n".join(artifact_sections))

    sections.append(
        "When previous artifacts conflict, prefer the most specific and most recent node output. "
        "Keep the final answer concise enough to be reused by another agent node."
    )
    return "\n\n".join(section for section in sections if section).strip()


def _output_title(node, key):
    if node.node_type == "analysis":
        return "Requirements report"
    if node.node_type == "planning":
        return "Chapter plan"
    if node.node_type == "writing":
        chapter_title = (node.metadata or {}).get("chapter_title") or (node.chapter.title if node.chapter_id and node.chapter else "")
        return f"Draft: {chapter_title}" if chapter_title else "Chapter draft"
    if node.node_type == "review":
        return "Review report"
    return key.replace("-", " ").title()


def _build_output_payload(workflow: MultiAgentWorkflow, node, run, output_key):
    return {
        "workflow_id": workflow.id,
        "workflow_title": workflow.title,
        "node_key": node.key,
        "node_label": node.label,
        "node_type": node.node_type,
        "output_key": output_key,
        "agent_run_id": run.id,
        "agent_slug": node.agent.slug if node.agent_id and node.agent else None,
        "chapter_id": node.chapter_id,
        "chapter_title": (node.metadata or {}).get("chapter_title") or (node.chapter.title if node.chapter_id and node.chapter else None),
        "status": run.status,
        "answer": run.answer,
        "error": run.error,
        "tools_used": list(run.tools_used or []),
        "step_count": run.step_count,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _count_completed_top_level_chapters(bid):
    count = 0
    for chapter in bid.chapters.filter(parent__isnull=True).only("content"):
        if chapter.content:
            count += 1
    return count


def _refresh_bid_progress(bid, *, workflow_done=False):
    completed = _count_completed_top_level_chapters(bid)
    bid.completed_chapters = completed
    bid.status = "active"
    bid.save(update_fields=["completed_chapters", "status", "updated_at"])

    draft_step = bid.steps.filter(order=2).first()
    review_step = bid.steps.filter(order=3).first()
    export_step = bid.steps.filter(order=4).first()

    if draft_step and completed:
        draft_step.status = "completed"
        draft_step.save(update_fields=["status", "updated_at"])

    if review_step and workflow_done:
        review_step.status = "completed"
        review_step.save(update_fields=["status", "updated_at"])

    if export_step and workflow_done:
        export_step.status = "active"
        export_step.save(update_fields=["status", "updated_at"])


def _persist_node_outputs(workflow: MultiAgentWorkflow, node, run):
    output_keys = list(node.output_artifacts or []) or [f"node-output-{node.key}"]
    artifact_type = "markdown" if run.answer else "json"
    for output_key in output_keys:
        WorkflowArtifact.objects.update_or_create(
            workflow=workflow,
            key=output_key,
            defaults={
                "node": node,
                "title": _output_title(node, output_key),
                "artifact_type": artifact_type,
                "payload": _build_output_payload(workflow, node, run, output_key),
            },
        )

    if node.node_type == "writing" and node.chapter_id and run.answer:
        chapter = node.chapter or BidChapter.objects.get(id=node.chapter_id)
        chapter.content = text_to_canvas_format(run.answer)
        chapter.save(update_fields=["content", "updated_at"])

    _refresh_bid_progress(workflow.bid, workflow_done=False)


def execute_workflow(workflow: MultiAgentWorkflow):
    nodes = list(workflow.nodes.select_related("agent", "chapter").order_by("order", "id"))
    if not nodes:
        workflow.status = "failed"
        workflow.error = "Workflow has no nodes to execute."
        workflow.completed_at = timezone.now()
        workflow.save(update_fields=["status", "error", "completed_at", "updated_at"])
        return workflow

    workflow.status = "running"
    workflow.error = ""
    workflow.current_node_key = ""
    workflow.completed_nodes = 0
    workflow.started_at = workflow.started_at or timezone.now()
    workflow.completed_at = None
    workflow.save(update_fields=["status", "error", "current_node_key", "completed_nodes", "started_at", "completed_at", "updated_at"])
    _refresh_bid_progress(workflow.bid, workflow_done=False)

    reference_file_ids = _reference_file_ids(workflow)

    for node in nodes:
        if _workflow_is_cancelled(workflow):
            return workflow

        dependencies = set(node.depends_on or [])
        completed_keys = {
            completed.key
            for completed in workflow.nodes.filter(status="done").only("key")
        }
        missing = sorted(dependencies - completed_keys)
        if missing:
            node.status = "failed"
            node.error = f"Dependencies not completed: {', '.join(missing)}"
            node.completed_at = timezone.now()
            node.save(update_fields=["status", "error", "completed_at", "updated_at"])
            workflow.status = "failed"
            workflow.error = node.error
            workflow.current_node_key = node.key
            workflow.completed_at = timezone.now()
            workflow.save(update_fields=["status", "error", "current_node_key", "completed_at", "updated_at"])
            return workflow

        artifact_map = {artifact.key: artifact for artifact in workflow.artifacts.all()}
        task = _build_node_task(workflow, node, artifact_map)
        max_steps = node.agent.default_max_steps if node.agent_id and node.agent else DEFAULT_MAX_STEPS
        agent_run = AgentRun.objects.create(
            user=workflow.user,
            agent=node.agent,
            task=task,
            status="pending",
            max_steps=max_steps,
            file_ids=reference_file_ids,
        )
        agent_run.session_id = f"u{workflow.user_id}-wf{workflow.id}-{node.key}"
        agent_run.save(update_fields=["session_id", "updated_at"])
        ensure_run_mission_artifact(agent_run)

        node.status = "running"
        node.error = ""
        node.summary = ""
        node.started_at = timezone.now()
        node.completed_at = None
        node.agent_run = agent_run
        node.save(update_fields=["status", "error", "summary", "started_at", "completed_at", "agent_run", "updated_at"])

        workflow.current_node_key = node.key
        workflow.save(update_fields=["current_node_key", "updated_at"])

        hermes = HermesService(session_id=agent_run.session_id)
        for _event in run_agent_loop(agent_run, hermes, max_steps=agent_run.max_steps):
            if _workflow_is_cancelled(workflow):
                agent_run.update_status_atomic("cancelled", completed_at=timezone.now())
                agent_run.refresh_from_db()
                ensure_run_mission_artifact(agent_run)
                node.status = "cancelled"
                node.error = WORKFLOW_CANCELLED_NOTICE
                node.completed_at = timezone.now()
                node.save(update_fields=["status", "error", "completed_at", "updated_at"])
                return workflow

        agent_run.refresh_from_db()

        if agent_run.status != "done":
            node.status = "failed" if agent_run.status != "cancelled" else "cancelled"
            node.error = agent_run.error or (WORKFLOW_CANCELLED_NOTICE if agent_run.status == "cancelled" else "Node execution failed.")
            node.summary = agent_run.answer[:400]
            node.completed_at = timezone.now()
            node.save(update_fields=["status", "error", "summary", "completed_at", "updated_at"])

            workflow.status = "cancelled" if agent_run.status == "cancelled" else "failed"
            workflow.error = node.error
            workflow.completed_at = timezone.now()
            workflow.current_node_key = node.key
            workflow.save(update_fields=["status", "error", "completed_at", "current_node_key", "updated_at"])
            return workflow

        node.status = "done"
        node.error = ""
        node.summary = (agent_run.answer or "")[:600]
        node.completed_at = timezone.now()
        node.save(update_fields=["status", "error", "summary", "completed_at", "updated_at"])

        _persist_node_outputs(workflow, node, agent_run)

        workflow.completed_nodes = workflow.nodes.filter(status="done").count()
        workflow.save(update_fields=["completed_nodes", "updated_at"])

    workflow.status = "done"
    workflow.error = ""
    workflow.completed_nodes = workflow.nodes.filter(status="done").count()
    workflow.current_node_key = nodes[-1].key
    workflow.completed_at = timezone.now()
    workflow.save(update_fields=["status", "error", "completed_nodes", "current_node_key", "completed_at", "updated_at"])
    _refresh_bid_progress(workflow.bid, workflow_done=True)
    return workflow
