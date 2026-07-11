from django.db import transaction

from apps.agents.models import Agent, MultiAgentWorkflow, WorkflowArtifact, WorkflowNodeRun
from apps.files.models import UploadedFile

DEFAULT_WORKFLOW_KIND = "bid_pipeline"

DEFAULT_AGENT_SPECS = {
    "tender-analyzer": {
        "name": "Tender Analyzer",
        "skill": "bid-writing/tender-analyzer",
        "max_steps": 8,
    },
    "chapter-planner": {
        "name": "Chapter Planner",
        "skill": "bid-writing/chapter-planner",
        "max_steps": 8,
    },
    "chapter-writer": {
        "name": "Chapter Writer",
        "skill": "bid-writing/bid-chapter-writer",
        "max_steps": 10,
    },
    "compliance-reviewer": {
        "name": "Compliance Reviewer",
        "skill": "bid-writing/compliance-reviewer",
        "max_steps": 8,
    },
}


def ensure_default_workflow_agents():
    agents = {}
    for slug, spec in DEFAULT_AGENT_SPECS.items():
        agent, _created = Agent.objects.get_or_create(
            slug=slug,
            defaults={
                "name": spec["name"],
                "skill": spec["skill"],
                "default_max_steps": spec["max_steps"],
                "is_active": True,
            },
        )
        changed = False
        if agent.name != spec["name"]:
            agent.name = spec["name"]
            changed = True
        if agent.skill != spec["skill"]:
            agent.skill = spec["skill"]
            changed = True
        if agent.default_max_steps != spec["max_steps"]:
            agent.default_max_steps = spec["max_steps"]
            changed = True
        if not agent.is_active:
            agent.is_active = True
            changed = True
        if changed:
            agent.save(update_fields=["name", "skill", "default_max_steps", "is_active", "updated_at"])
        agents[slug] = agent
    return agents


def _serialize_chapters(bid, include_child_chapters=False):
    chapters = bid.chapters.order_by("order", "id")
    if not include_child_chapters:
        chapters = chapters.filter(parent__isnull=True)
    return [
        {
            "id": chapter.id,
            "parent_id": chapter.parent_id,
            "title": chapter.title,
            "order": chapter.order,
        }
        for chapter in chapters
    ]


def _serialize_steps(bid):
    return [
        {
            "id": step.id,
            "label": step.label,
            "order": step.order,
            "status": step.status,
        }
        for step in bid.steps.order_by("order", "id")
    ]


def _serialize_recent_files(user, limit=10):
    files = UploadedFile.objects.filter(user=user).order_by("-created_at", "-id")[:limit]
    return [
        {
            "id": item.id,
            "name": item.original_name,
            "type": item.file_type,
            "size": item.file_size,
            "created_at": item.created_at.isoformat(),
        }
        for item in files
    ]


def _create_workflow_artifacts(workflow, bid_snapshot, recent_files):
    WorkflowArtifact.objects.bulk_create(
        [
            WorkflowArtifact(
                workflow=workflow,
                key="bid_snapshot",
                title="Bid snapshot",
                artifact_type="json",
                payload=bid_snapshot,
            ),
            WorkflowArtifact(
                workflow=workflow,
                key="reference_files",
                title="Recent reference files",
                artifact_type="json",
                payload={"files": recent_files},
            ),
        ]
    )


def _build_node_blueprint(workflow, agents, chapters):
    nodes = [
        WorkflowNodeRun(
            workflow=workflow,
            agent=agents["tender-analyzer"],
            key="analyzer",
            label="Analyze tender requirements",
            node_type="analysis",
            order=10,
            depends_on=[],
            input_artifacts=["bid_snapshot", "reference_files"],
            output_artifacts=["requirements_report"],
        ),
        WorkflowNodeRun(
            workflow=workflow,
            agent=agents["chapter-planner"],
            key="planner",
            label="Plan chapter strategy",
            node_type="planning",
            order=20,
            depends_on=["analyzer"],
            input_artifacts=["bid_snapshot", "requirements_report"],
            output_artifacts=["chapter_plan"],
        ),
    ]

    writer_keys = []
    order = 30
    for chapter in chapters:
        key = f"writer-{chapter['id']}"
        writer_keys.append(key)
        nodes.append(
            WorkflowNodeRun(
                workflow=workflow,
                agent=agents["chapter-writer"],
                chapter_id=chapter["id"],
                key=key,
                label=f"Draft chapter: {chapter['title']}",
                node_type="writing",
                order=order,
                depends_on=["planner"],
                input_artifacts=["bid_snapshot", "chapter_plan", "requirements_report"],
                output_artifacts=[f"chapter-draft-{chapter['id']}"],
                metadata={"chapter_title": chapter["title"]},
            )
        )
        order += 10

    nodes.append(
        WorkflowNodeRun(
            workflow=workflow,
            agent=agents["compliance-reviewer"],
            key="reviewer",
            label="Review compliance and consistency",
            node_type="review",
            order=order,
            depends_on=writer_keys,
            input_artifacts=["bid_snapshot", "requirements_report", "chapter_plan", *[f"chapter-draft-{chapter['id']}" for chapter in chapters]],
            output_artifacts=["review_report"],
        )
    )
    return nodes


def create_bid_workflow(*, bid, user, objective="", include_child_chapters=False):
    agents = ensure_default_workflow_agents()
    chapters = _serialize_chapters(bid, include_child_chapters=include_child_chapters)
    bid_snapshot = {
        "bid_id": bid.id,
        "title": bid.title,
        "status": bid.status,
        "completed_chapters": bid.completed_chapters,
        "total_chapters": bid.total_chapters,
        "chapters": chapters,
        "steps": _serialize_steps(bid),
    }
    recent_files = _serialize_recent_files(user)
    objective_text = (objective or "").strip() or f"Analyze, plan, draft, and review the bid document for {bid.title}."

    with transaction.atomic():
        workflow = MultiAgentWorkflow.objects.create(
            user=user,
            bid=bid,
            kind=DEFAULT_WORKFLOW_KIND,
            title=f"{bid.title} multi-agent workflow",
            objective=objective_text,
            status="pending",
            metadata={
                "chapter_count": len(chapters),
                "recent_file_count": len(recent_files),
                "include_child_chapters": include_child_chapters,
            },
        )
        _create_workflow_artifacts(workflow, bid_snapshot, recent_files)
        nodes = _build_node_blueprint(workflow, agents, chapters)
        WorkflowNodeRun.objects.bulk_create(nodes)
        workflow.node_count = len(nodes)
        workflow.save(update_fields=["node_count", "updated_at"])

    return workflow
