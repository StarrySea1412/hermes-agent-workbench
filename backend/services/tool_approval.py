"""Server-side per-call permissions, not an OS isolation boundary.

Only python_sandbox is gated. Context is supplied by the service, never merged
with model arguments. Decisions only change rows; the originating worker runs.
"""
import json
import time
from datetime import timedelta

from django.utils import timezone

from apps.agents.models import AgentRun
from apps.projects.models import Conversation
from apps.tools.models import ToolExecution
from services.chat_cancel import TurnCancelled

APPROVAL_TIMEOUT = 120
POLL_INTERVAL = 0.1
ACTIVE = ("pending", "approved", "running")


class ApprovalUnavailable(RuntimeError):
    pass


def resolve_binding(context):
    """Resolve trusted service IDs and latch controlled mode for this turn."""
    context = context or {}
    user = context.get("user")
    cid, rid = context.get("conversation_id"), context.get("run_id")
    required = bool(context.get("tool_approval_required"))
    run = None
    if rid is not None:
        run = AgentRun.objects.select_related("conversation").filter(pk=rid, user=user).first()
        if run is None:
            raise ApprovalUnavailable("工具上下文缺少有效的运行记录。")
        if cid is not None and run.conversation_id != cid:
            raise ApprovalUnavailable("工具运行与会话不匹配。")
        cid = run.conversation_id
    conversation = None
    if cid is not None:
        conversation = Conversation.objects.filter(pk=cid, user=user).first()
        if conversation is None:
            raise ApprovalUnavailable("工具上下文缺少有效的会话。")
        required = required or conversation.tool_approval_required
    if required:
        if run is None or conversation is None or run.conversation_id != conversation.pk:
            raise ApprovalUnavailable("审批模式需要绑定有效的会话和运行记录。")
        context["tool_approval_required"] = True
        return run, conversation
    return None


def check_cancelled(context, binding):
    callback = context.get("should_cancel")
    run, conversation = binding
    if ((callback and callback()) or not AgentRun.objects.filter(
        pk=run.pk, user_id=run.user_id, conversation_id=conversation.pk,
        status="running", conversation__cancel_requested=False,
    ).exists()):
        raise TurnCancelled("已停止审批模式运行。")


def reconcile(queryset):
    """Lazy recovery also handles a worker that died without running finally."""
    queryset.filter(status__in=ACTIVE).exclude(run__status="running").update(
        status="cancelled", error="运行已结束。")
    queryset.filter(status__in=ACTIVE, conversation__cancel_requested=True).update(
        status="cancelled", error="运行已取消。")
    queryset.filter(status__in=("pending", "approved"), expires_at__lte=timezone.now()).update(
        status="expired", error="审批已过期。")


def close_run_executions(run_id, status="failed"):
    ToolExecution.objects.filter(run_id=run_id, status__in=ACTIVE).update(
        status=status, error="运行已取消。" if status == "cancelled" else "工具工作线程已结束。")


def approval_payload(execution):
    return {
        "id": str(execution.pk), "conversation_id": execution.conversation_id,
        "run_id": execution.run_id, "tool_name": execution.tool_name,
        "arguments": execution.arguments, "status": execution.status,
        "expires_at": execution.expires_at.isoformat(),
    }


def execute_approved(name, arguments, context, handler, binding):
    check_cancelled(context, binding)
    run, conversation = binding
    # JSON roundtrip severs mutable references owned by the model/event consumer.
    execution = ToolExecution.objects.create(
        user_id=run.user_id, conversation_id=conversation.pk, run_id=run.pk,
        tool_name=name, arguments=json.loads(json.dumps(arguments or {})),
        expires_at=timezone.now() + timedelta(seconds=APPROVAL_TIMEOUT),
    )
    rows = ToolExecution.objects.filter(pk=execution.pk)
    deadline = time.monotonic() + APPROVAL_TIMEOUT
    try:
        on_event = context.get("on_event")
        if on_event:
            on_event("tool_approval", approval_payload(execution))
        while True:
            check_cancelled(context, binding)
            reconcile(rows)
            if time.monotonic() >= deadline:
                rows.filter(status__in=("pending", "approved")).update(status="expired", error="审批已过期。")
            execution.refresh_from_db()
            if execution.status == "approved":
                # Compare-and-swap: no transaction/lock is held while waiting or executing.
                claimed = rows.filter(
                    status="approved", decision="allow", expires_at__gt=timezone.now(),
                    run__status="running", conversation__cancel_requested=False,
                ).update(status="running")
                if not claimed:
                    continue
                execution.refresh_from_db()  # execute only the persisted, approved arguments
                check_cancelled(context, binding)
                result = handler(execution.arguments, context)
                check_cancelled(context, binding)
                rows.filter(status="running").update(
                    status="succeeded" if result.get("ok") else "failed", result=result,
                    error="" if result.get("ok") else "工具执行失败。",
                )
                return result
            if execution.status != "pending":
                return {"ok": False, "error": execution.error or f"工具审批状态：{execution.status}",
                        "tool_execution_id": str(execution.pk)}
            time.sleep(POLL_INTERVAL)
    except TurnCancelled:
        rows.filter(status__in=ACTIVE).update(status="cancelled", error="运行已取消。")
        raise
    except Exception:
        rows.filter(status__in=ACTIVE).update(status="failed", error="工具执行失败。")
        raise ApprovalUnavailable("审批工具执行失败。") from None
    finally:
        rows.filter(status__in=ACTIVE).update(status="failed", error="工具工作线程已结束。")
