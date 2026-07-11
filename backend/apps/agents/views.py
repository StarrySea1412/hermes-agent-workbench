import json

from django.db.models import Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from apps.agents.models import Agent, AgentArtifact, AgentMemory, AgentRun, MultiAgentWorkflow
from apps.agents.orchestrator import (
    DEFAULT_MAX_STEPS,
    ensure_run_mission_artifact,
    get_run_files,
    get_run_memories,
    run_agent_loop,
)
from apps.agents.serializers import (
    AgentArtifactSerializer,
    AgentMemorySerializer,
    AgentMemoryUpsertSerializer,
    AgentRunArtifactSerializer,
    AgentRunDetailSerializer,
    AgentRunListSerializer,
    AgentSerializer,
    AgentUpsertSerializer,
    CreateAgentRunSerializer,
    CreateMultiAgentWorkflowSerializer,
    MultiAgentWorkflowDetailSerializer,
    MultiAgentWorkflowListSerializer,
    SaveRunMemorySerializer,
)
from apps.agents.workflows import WORKFLOW_CANCELLED_NOTICE, create_bid_workflow, execute_workflow
from apps.bids.models import Bid
from apps.files.models import UploadedFile
from apps.tools import schemas
from services.hermes_service import HermesService

DEFAULT_AGENT_TEMPLATES = [
    {
        "slug": "general-operator",
        "name": "通用执行器",
        "skill": "agent-engineering/general-operator",
        "system_prompt": "以谨慎的通用智能体方式执行任务。把工作拆成明确步骤，并只在工具确实有价值时调用它们。",
        "default_max_steps": 8,
        "allowed_tools": [],
    },
    {
        "slug": "research-scout",
        "name": "研究侦察员",
        "skill": "agent-engineering/research-scout",
        "system_prompt": "优先进行证据收集、信息综合和风险追踪，并为工程师返回结构化结论。",
        "default_max_steps": 10,
        "allowed_tools": ["web_search", "doc_parse"],
    },
    {
        "slug": "artifact-builder",
        "name": "产物构建器",
        "skill": "agent-engineering/artifact-builder",
        "system_prompt": "把研究结论转化为具体产物，例如计划、规格说明、草稿或可直接导出的结构化输出。",
        "default_max_steps": 8,
        "allowed_tools": ["doc_parse", "doc_export"],
    },
]


def _get_user_bid_or_404(request, bid_id):
    return get_object_or_404(Bid.objects.filter(user=request.user), id=bid_id)


def _ensure_default_agents():
    for payload in DEFAULT_AGENT_TEMPLATES:
        agent, created = Agent.objects.get_or_create(
            slug=payload["slug"],
            defaults={
                "name": payload["name"],
                "skill": payload["skill"],
                "system_prompt": payload["system_prompt"],
                "default_max_steps": payload["default_max_steps"],
                "allowed_tools": payload["allowed_tools"],
                "is_active": True,
            },
        )
        if created:
            continue
        dirty = False
        if not agent.skill and payload["skill"]:
            agent.skill = payload["skill"]
            dirty = True
        if not agent.allowed_tools and payload["allowed_tools"]:
            agent.allowed_tools = payload["allowed_tools"]
            dirty = True
        if dirty:
            agent.save(update_fields=["skill", "allowed_tools", "updated_at"])


def _get_user_run_or_404(request, run_id):
    return get_object_or_404(
        AgentRun.objects.select_related("agent").prefetch_related("steps", "artifacts").filter(user=request.user),
        id=run_id,
    )


def _get_user_workflow_or_404(request, bid_id, workflow_id):
    _get_user_bid_or_404(request, bid_id)
    return get_object_or_404(
        MultiAgentWorkflow.objects.select_related("bid").prefetch_related("nodes__agent", "nodes__chapter", "artifacts").filter(
            user=request.user,
            bid_id=bid_id,
        ),
        id=workflow_id,
    )


def _normalize_memory_ids(values):
    items = []
    seen = set()
    for value in values or []:
        try:
            current = int(value)
        except (TypeError, ValueError):
            continue
        if current <= 0 or current in seen:
            continue
        seen.add(current)
        items.append(current)
    return items


def _validate_memory_ids(user, memory_ids):
    normalized = _normalize_memory_ids(memory_ids)
    if not normalized:
        return []
    matches = AgentMemory.objects.filter(user=user, id__in=normalized).values_list("id", flat=True)
    found = list(matches)
    if len(found) != len(normalized):
        raise ValidationError({"memory_ids": "One or more memories are not available for this user."})
    return normalized


def _validate_file_ids(user, file_ids):
    normalized = _normalize_memory_ids(file_ids)
    if not normalized:
        return []
    matches = UploadedFile.objects.filter(user=user, id__in=normalized).values_list("id", flat=True)
    found = list(matches)
    if len(found) != len(normalized):
        raise ValidationError({"file_ids": "One or more files are not available for this user."})
    return normalized


def _build_legacy_run_artifacts(run):
    attached_files = [{
        "id": uploaded.id,
        "original_name": uploaded.original_name,
        "file_type": uploaded.file_type,
        "file_size": uploaded.file_size,
        "description": uploaded.description,
        "file_url": uploaded.file.url if uploaded.file else None,
    } for uploaded in get_run_files(run)]

    artifacts = [{
        "id": None,
        "run_id": run.id,
        "step_id": None,
        "key": "mission",
        "title": "任务",
        "artifact_type": "task",
        "source": "system",
        "payload": {
            "task": run.task,
            "status": run.status,
            "template": run.agent.name if run.agent_id and run.agent else None,
            "session_id": run.session_id,
            "max_steps": run.max_steps,
            "memory_ids": run.memory_ids,
            "file_ids": run.file_ids,
            "attached_files": attached_files,
        },
        "metadata": {
            "step_count": run.step_count,
            "tools_used": run.tools_used,
        },
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }]

    if run.answer:
        artifacts.append({
            "id": None,
            "run_id": run.id,
            "step_id": None,
            "key": "final-answer",
            "title": "最终回答",
            "artifact_type": "answer",
            "source": "agent",
            "payload": {"answer": run.answer},
            "metadata": {},
            "created_at": run.completed_at or run.updated_at,
            "updated_at": run.updated_at,
        })

    for step in run.steps.all():
        if step.type == "tool_result" and step.tool_result is not None:
            artifacts.append({
                "id": None,
                "run_id": run.id,
                "step_id": step.id,
                "key": f"tool-result-step-{step.id}",
                "title": f"工具结果：{step.tool_name or 'unknown'}",
                "artifact_type": "tool_result",
                "source": step.tool_name or "tool",
                "payload": step.tool_result,
                "metadata": {"step_order": step.order, "step_status": step.status},
                "created_at": step.created_at,
                "updated_at": step.created_at,
            })
        elif step.type == "plan" and step.content:
            artifacts.append({
                "id": None,
                "run_id": run.id,
                "step_id": step.id,
                "key": f"plan-step-{step.id}",
                "title": "计划快照",
                "artifact_type": "plan",
                "source": "planner",
                "payload": step.content,
                "metadata": {"step_order": step.order, "step_status": step.status},
                "created_at": step.created_at,
                "updated_at": step.created_at,
            })
        elif step.type == "answer" and step.content:
            artifacts.append({
                "id": None,
                "run_id": run.id,
                "step_id": step.id,
                "key": "final-answer",
                "title": "最终回答",
                "artifact_type": "answer",
                "source": "agent",
                "payload": step.content,
                "metadata": {"step_order": step.order, "step_status": step.status},
                "created_at": step.created_at,
                "updated_at": step.created_at,
            })
        elif step.type == "error" and step.content:
            artifacts.append({
                "id": None,
                "run_id": run.id,
                "step_id": step.id,
                "key": f"error-step-{step.id}",
                "title": "运行错误",
                "artifact_type": "error",
                "source": "system",
                "payload": step.content,
                "metadata": {"step_order": step.order, "step_status": step.status},
                "created_at": step.created_at,
                "updated_at": step.created_at,
            })

    return artifacts


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agent_templates(request):
    _ensure_default_agents()
    agents = Agent.objects.order_by("name")
    return Response(AgentSerializer(agents, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_agent_template(request):
    serializer = AgentUpsertSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    agent = serializer.save()
    return Response(AgentSerializer(agent).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def agent_template_detail(request, agent_id):
    _ensure_default_agents()
    agent = get_object_or_404(Agent.objects.all(), id=agent_id)

    if request.method == "GET":
        return Response(AgentSerializer(agent).data)

    if request.method == "PATCH":
        serializer = AgentUpsertSerializer(agent, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        agent.refresh_from_db()
        return Response(AgentSerializer(agent).data)

    agent.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agent_tools(request):
    return Response(schemas.tool_catalog())


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def agent_memories(request):
    if request.method == "GET":
        queryset = AgentMemory.objects.filter(user=request.user).select_related("run")

        scope = (request.GET.get("scope") or "").strip()
        if scope:
            queryset = queryset.filter(scope=scope)

        run_id = (request.GET.get("run_id") or "").strip()
        if run_id.isdigit():
            queryset = queryset.filter(run_id=int(run_id))

        pinned = (request.GET.get("pinned") or "").strip().lower()
        if pinned in {"true", "false"}:
            queryset = queryset.filter(pinned=(pinned == "true"))

        query_text = (request.GET.get("query") or "").strip()
        if query_text:
            queryset = queryset.filter(Q(title__icontains=query_text) | Q(content__icontains=query_text))

        queryset = queryset.order_by("-pinned", "-last_used_at", "-updated_at", "-id")
        return Response(AgentMemorySerializer(queryset, many=True).data)

    serializer = AgentMemoryUpsertSerializer(data=request.data, context={"user": request.user})
    serializer.is_valid(raise_exception=True)
    memory = serializer.save()
    return Response(AgentMemorySerializer(memory).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def agent_memory_detail(request, memory_id):
    memory = get_object_or_404(AgentMemory.objects.filter(user=request.user), id=memory_id)

    if request.method == "GET":
        return Response(AgentMemorySerializer(memory).data)

    if request.method == "PATCH":
        serializer = AgentMemoryUpsertSerializer(memory, data=request.data, partial=True, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        memory.refresh_from_db()
        return Response(AgentMemorySerializer(memory).data)

    memory.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def agent_runs(request):
    if request.method == "GET":
        runs = AgentRun.objects.select_related("agent").filter(user=request.user).order_by("-created_at")
        return Response(AgentRunListSerializer(runs, many=True).data)

    _ensure_default_agents()
    serializer = CreateAgentRunSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    agent = None
    agent_id = serializer.validated_data.get("agent_id")
    if agent_id:
        agent = get_object_or_404(Agent.objects.filter(is_active=True), id=agent_id)

    memory_ids = _validate_memory_ids(request.user, serializer.validated_data.get("memory_ids"))
    file_ids = _validate_file_ids(request.user, serializer.validated_data.get("file_ids"))
    max_steps = serializer.validated_data.get("max_steps") or (agent.default_max_steps if agent else DEFAULT_MAX_STEPS)
    run = AgentRun.objects.create(
        user=request.user,
        agent=agent,
        task=serializer.validated_data["task"],
        status="pending",
        max_steps=max_steps,
        memory_ids=memory_ids,
        file_ids=file_ids,
    )
    run.session_id = f"u{request.user.id}-run{run.id}"
    run.save(update_fields=["session_id", "updated_at"])
    run.refresh_from_db()
    ensure_run_mission_artifact(run)

    return Response(AgentRunDetailSerializer(run, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agent_run_detail(request, run_id):
    run = _get_user_run_or_404(request, run_id)
    return Response(AgentRunDetailSerializer(run, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agent_run_artifacts(request, run_id):
    run = _get_user_run_or_404(request, run_id)
    artifacts = list(run.artifacts.all())
    if artifacts:
        return Response(AgentArtifactSerializer(artifacts, many=True).data)
    return Response(AgentRunArtifactSerializer(_build_legacy_run_artifacts(run), many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agent_run_memories(request, run_id):
    run = _get_user_run_or_404(request, run_id)
    memories = get_run_memories(run)
    return Response(AgentMemorySerializer(memories, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def agent_run_save_memory(request, run_id):
    run = _get_user_run_or_404(request, run_id)
    serializer = SaveRunMemorySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    content = (serializer.validated_data.get("content") or run.answer or "").strip()
    if not content:
        return Response(
            {"message": "这次运行还没有最终回答。请先提供自定义内容，或等待运行完成后再保存。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    title = (serializer.validated_data.get("title") or "").strip() or f"运行洞察：{run.task[:48]}"
    memory = AgentMemory.objects.create(
        user=request.user,
        run=run,
        title=title,
        content=content,
        scope=serializer.validated_data.get("scope") or "workspace",
        tags=serializer.validated_data.get("tags") or [],
        pinned=serializer.validated_data.get("pinned", False),
        metadata={
            "source": "run_final_answer",
            "run_id": run.id,
            "run_status": run.status,
            "agent_slug": run.agent.slug if run.agent_id and run.agent else None,
        },
    )
    return Response(AgentMemorySerializer(memory).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_agent_run(request, run_id):
    run = _get_user_run_or_404(request, run_id)

    if run.status == "cancelled":
        return Response(AgentRunDetailSerializer(run, context={"request": request}).data)

    if run.status not in {"pending", "running"}:
        return Response(
            {"message": f"当前运行状态为 {run.status}，无法取消。"},
            status=status.HTTP_409_CONFLICT,
        )

    run.update_status_atomic("cancelled", completed_at=timezone.now())
    run.refresh_from_db()
    ensure_run_mission_artifact(run)
    return Response(AgentRunDetailSerializer(run, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def execute_agent_run_stream(request, run_id):
    run = _get_user_run_or_404(request, run_id)

    if run.status == "running":
        return Response(
            {"message": "运行已经在执行中。"},
            status=status.HTTP_409_CONFLICT,
        )

    if run.status in {"done", "failed", "cancelled"}:
        return Response(
            {"message": f"当前运行状态已是 {run.status}。如需再次执行，请新建一次运行。"},
            status=status.HTTP_409_CONFLICT,
        )

    session_id = run.session_id or f"u{request.user.id}-run{run.id}"
    if run.session_id != session_id:
        run.session_id = session_id
        run.save(update_fields=["session_id", "updated_at"])
    ensure_run_mission_artifact(run)

    health = HermesService(session_id=session_id).health_check()
    if not health.get("connected"):
        return Response(
            {"message": health.get("error") or "Hermes 网关当前不可用。"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def event_stream():
        yield _sse("run", AgentRunListSerializer(run).data)
        hermes = HermesService(session_id=session_id)
        for event in run_agent_loop(run, hermes, max_steps=run.max_steps):
            yield _sse("step", event)
        run.refresh_from_db()
        yield _sse("complete", AgentRunDetailSerializer(run, context={"request": request}).data)

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def bid_multi_agent_workflows(request, bid_id):
    bid = _get_user_bid_or_404(request, bid_id)

    if request.method == "GET":
        workflows = bid.multi_agent_workflows.order_by("-created_at")
        return Response(MultiAgentWorkflowListSerializer(workflows, many=True).data)

    serializer = CreateMultiAgentWorkflowSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    workflow = create_bid_workflow(
        bid=bid,
        user=request.user,
        objective=serializer.validated_data.get("objective") or "",
        include_child_chapters=serializer.validated_data.get("include_child_chapters", False),
    )
    return Response(MultiAgentWorkflowDetailSerializer(workflow).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bid_multi_agent_workflow_detail(request, bid_id, workflow_id):
    workflow = _get_user_workflow_or_404(request, bid_id, workflow_id)
    return Response(MultiAgentWorkflowDetailSerializer(workflow).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def execute_bid_multi_agent_workflow(request, bid_id, workflow_id):
    workflow = _get_user_workflow_or_404(request, bid_id, workflow_id)

    if workflow.status == "running":
        return Response(
            {"message": "工作流已经在执行中。"},
            status=status.HTTP_409_CONFLICT,
        )

    if workflow.status in {"done", "failed", "cancelled"}:
        return Response(
            {"message": f"当前工作流状态已是 {workflow.status}。如需再次执行，请新建一个工作流蓝图。"},
            status=status.HTTP_409_CONFLICT,
        )

    health = HermesService(session_id=f"u{request.user.id}-wf{workflow.id}").health_check()
    if not health.get("connected"):
        return Response(
            {"message": health.get("error") or "Hermes 网关当前不可用。"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    execute_workflow(workflow)
    workflow = _get_user_workflow_or_404(request, bid_id, workflow_id)
    return Response(MultiAgentWorkflowDetailSerializer(workflow).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_bid_multi_agent_workflow(request, bid_id, workflow_id):
    workflow = _get_user_workflow_or_404(request, bid_id, workflow_id)

    if workflow.status == "cancelled":
        return Response(MultiAgentWorkflowDetailSerializer(workflow).data)

    if workflow.status not in {"pending", "running"}:
        return Response(
            {"message": f"当前工作流状态为 {workflow.status}，无法取消。"},
            status=status.HTTP_409_CONFLICT,
        )

    active_node = workflow.nodes.filter(status="running").select_related("agent_run").order_by("order", "id").first()
    if active_node and active_node.agent_run_id:
        active_node.agent_run.update_status_atomic("cancelled", completed_at=timezone.now())
        active_node.agent_run.refresh_from_db()
        ensure_run_mission_artifact(active_node.agent_run)
        active_node.status = "cancelled"
        active_node.error = WORKFLOW_CANCELLED_NOTICE
        active_node.completed_at = timezone.now()
        active_node.save(update_fields=["status", "error", "completed_at", "updated_at"])

    workflow.update_status_atomic("cancelled", completed_at=timezone.now(), error=WORKFLOW_CANCELLED_NOTICE)
    workflow.refresh_from_db()
    workflow = _get_user_workflow_or_404(request, bid_id, workflow_id)
    return Response(MultiAgentWorkflowDetailSerializer(workflow).data)


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
