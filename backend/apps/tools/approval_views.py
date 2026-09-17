from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.projects.models import Conversation
from apps.tools.models import ToolExecution, WorkspaceWrite
from services.tool_approval import reconcile


class ToolExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolExecution
        fields = ["id", "conversation_id", "run_id", "tool_name", "arguments",
                  "status", "created_at", "expires_at", "error"]
        read_only_fields = fields


class WorkspaceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceWrite
        fields = ["id", "conversation_id", "run_id", "path", "diff", "status",
                  "applied", "created_at", "updated_at", "error"]
        read_only_fields = fields

    diff = serializers.SerializerMethodField()

    def get_diff(self, obj):
        import difflib

        return "".join(difflib.unified_diff(
            (obj.previous or "").splitlines(keepends=True), obj.proposed.splitlines(keepends=True),
            fromfile=f"a/{obj.path}", tofile=f"b/{obj.path}",
        ))


class ExecutionFilters(serializers.Serializer):
    conversation_id = serializers.IntegerField(min_value=1)
    run_id = serializers.IntegerField(min_value=1, required=False)
    status = serializers.ChoiceField(choices=ToolExecution.STATUS_CHOICES, required=False)


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["allow", "deny"])


def owned(request):
    return ToolExecution.objects.filter(
        user=request.user, conversation__user=request.user, run__user=request.user)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tool_executions(request):
    filters = ExecutionFilters(data=request.query_params)
    filters.is_valid(raise_exception=True)
    data = dict(filters.validated_data)
    get_object_or_404(Conversation, pk=data["conversation_id"], user=request.user)
    requested_status = data.pop("status", None)
    rows = owned(request).filter(**data)
    reconcile(rows)
    if requested_status:
        rows = rows.filter(status=requested_status)
    return Response(ToolExecutionSerializer(rows, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def tool_execution_decision(request, execution_id):
    serializer = DecisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    decision = serializer.validated_data["decision"]
    rows = owned(request).filter(pk=execution_id)
    get_object_or_404(rows)
    reconcile(rows)
    changed = rows.filter(
        status="pending", decision="", expires_at__gt=timezone.now(),
        run__status="running", conversation__cancel_requested=False,
    ).update(status="approved" if decision == "allow" else "denied", decision=decision,
             error="" if decision == "allow" else "用户拒绝了工具执行。")
    execution = get_object_or_404(rows)
    # A repeated identical decision is a read, never another execution. Terminal
    # expiry/cancellation cannot be resurrected even by an earlier allow.
    same = execution.decision == decision and execution.status not in ("expired", "cancelled")
    return Response(ToolExecutionSerializer(execution).data, status=200 if changed or same else 409)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_writes(request):
    conversation_id = request.query_params.get("conversation_id")
    rows = WorkspaceWrite.objects.filter(user=request.user).order_by("-created_at", "id")
    if conversation_id:
        rows = rows.filter(conversation_id=conversation_id)
    return Response(WorkspaceWriteSerializer(rows[:100], many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def workspace_write_rollback(request, write_id):
    """Roll back one applied write to its previous content; owner-only, idempotent."""
    rows = WorkspaceWrite.objects.filter(pk=write_id, user=request.user)
    write = get_object_or_404(rows)
    if write.status == "rolled_back":
        return Response(WorkspaceWriteSerializer(write).data, status=200)
    if write.status != "applied" or not write.applied:
        return Response({"message": f"仅已应用的写入可回滚（当前：{write.status}）。"}, status=409)
    from apps.tools.handlers.workspace_files import workspace_root

    root = workspace_root(write.user_id)
    target = (root / write.path).resolve()
    if root not in target.parents and target != root:
        return Response({"message": "路径越出工作区范围。"}, status=409)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(write.previous or "", encoding="utf-8")
    write.status = "rolled_back"
    write.save(update_fields=["status", "updated_at"])
    return Response(WorkspaceWriteSerializer(write).data, status=200)
