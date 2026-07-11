import json
import logging

from django.db.models import Q
from django.utils import timezone

from apps.agents.models import AgentArtifact, AgentMemory, AgentRun, AgentStep
from apps.files.models import UploadedFile
from apps.tools import registry, schemas
from services.hermes_service import HermesService
from services.tool_call_parser import parse_tool_calls

logger = logging.getLogger("api")

DEFAULT_MAX_STEPS = 8
DEFAULT_AGENT_SYSTEM_PROMPT = """You are Hermes Workbench, a practical multi-step agent for engineers.
Plan briefly, use tools when they improve accuracy, keep intermediate steps explicit, and finish with a concise final answer.
When you are unsure, make the smallest reasonable assumption and continue."""
CANCELLED_NOTICE = "运行已被用户取消。"


def _dedupe_ids(values):
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


def get_run_memories(run: AgentRun):
    memory_ids = _dedupe_ids(run.memory_ids)
    query = Q(run_id=run.id)
    if memory_ids:
        query |= Q(id__in=memory_ids)
    queryset = AgentMemory.objects.filter(user=run.user).filter(query).order_by(
        "-pinned",
        "-last_used_at",
        "-updated_at",
        "-id",
    )
    records = []
    seen = set()
    for memory in queryset:
        if memory.id in seen:
            continue
        seen.add(memory.id)
        records.append(memory)
    return records


def get_run_files(run: AgentRun):
    file_ids = _dedupe_ids(run.file_ids)
    if not file_ids:
        return []

    queryset = UploadedFile.objects.filter(user=run.user, id__in=file_ids)
    files_by_id = {uploaded.id: uploaded for uploaded in queryset}
    return [files_by_id[file_id] for file_id in file_ids if file_id in files_by_id]


def ensure_run_mission_artifact(run: AgentRun):
    attached_files = [
        {
            "id": uploaded.id,
            "original_name": uploaded.original_name,
            "file_type": uploaded.file_type,
            "file_size": uploaded.file_size,
            "description": uploaded.description,
            "file_url": uploaded.file.url if uploaded.file else None,
        }
        for uploaded in get_run_files(run)
    ]
    AgentArtifact.objects.update_or_create(
        run=run,
        key="mission",
        defaults={
            "user": run.user,
            "step": None,
            "title": "任务",
            "artifact_type": "task",
            "source": "system",
            "payload": {
                "task": run.task,
                "status": run.status,
                "template": run.agent.name if run.agent_id and run.agent else None,
                "session_id": run.session_id,
                "max_steps": run.max_steps,
                "memory_ids": _dedupe_ids(run.memory_ids),
                "file_ids": _dedupe_ids(run.file_ids),
                "attached_files": attached_files,
            },
            "metadata": {
                "step_count": run.step_count,
                "tools_used": list(run.tools_used or []),
            },
        },
    )


def _touch_memories(memories):
    if not memories:
        return
    timestamp = timezone.now()
    AgentMemory.objects.filter(id__in=[memory.id for memory in memories]).update(last_used_at=timestamp)


def _resolve_allowed_tool_names(run: AgentRun):
    configured = list(run.agent.allowed_tools or []) if run.agent_id and run.agent else []
    available = registry.list_tool_names()
    if not configured:
        return available
    allow_set = set(configured)
    return [name for name in available if name in allow_set]


def _build_memory_prompt(run: AgentRun):
    memories = get_run_memories(run)
    if not memories:
        return "", []

    lines = ["Active memory context:"]
    for memory in memories[:6]:
        tags = ", ".join(memory.tags or []) or "none"
        content = (memory.content or "").strip()
        if len(content) > 1200:
            content = f"{content[:1197]}..."
        lines.append(f"- [{memory.scope}] {memory.title}")
        lines.append(f"  Tags: {tags}")
        lines.append(f"  Content: {content}")
    lines.append("")
    return "\n".join(lines), memories


def _build_file_prompt(run: AgentRun):
    files = get_run_files(run)
    if not files:
        return "", []

    lines = ["Attached files available to this run:"]
    for uploaded in files[:8]:
        description = (uploaded.description or "").strip()
        if len(description) > 180:
            description = f"{description[:177]}..."
        line = f"- file_id={uploaded.id} | {uploaded.original_name} | type={uploaded.file_type} | size={uploaded.file_size_display}"
        if description:
            line = f"{line} | note={description}"
        lines.append(line)
    lines.append("Use doc_parse with a file_id when you need the file contents.")
    lines.append("")
    return "\n".join(lines), files


def _build_system_prompt(run, tools_prompt, memory_prompt):
    from apps.agents.skill_loader import build_system_prompt

    skill = run.agent.skill if run.agent and run.agent.skill else ""
    extra_prompt = run.agent.system_prompt if run.agent and run.agent.system_prompt else ""
    composed = build_system_prompt(skill, extra=extra_prompt, tools_prompt=tools_prompt)

    sections = [DEFAULT_AGENT_SYSTEM_PROMPT]
    if composed:
        sections.append(composed)
    elif tools_prompt:
        sections.append(tools_prompt)
    if memory_prompt:
        sections.append(memory_prompt)
    return "\n\n".join(section for section in sections if section).strip()


def _persist_step_artifact(step: AgentStep):
    run = step.run
    defaults = {
        "user": run.user,
        "run": run,
        "step": step,
        "metadata": {
            "step_order": step.order,
            "step_status": step.status,
        },
    }

    if step.type == "plan" and step.content:
        AgentArtifact.objects.update_or_create(
            run=run,
            key=f"plan-step-{step.id}",
            defaults={
                **defaults,
                "title": "计划快照",
                "artifact_type": "plan",
                "source": "planner",
                "payload": step.content,
            },
        )
    elif step.type == "tool_result" and step.tool_result is not None:
        AgentArtifact.objects.update_or_create(
            run=run,
            key=f"tool-result-step-{step.id}",
            defaults={
                **defaults,
                "title": f"工具结果：{step.tool_name or 'unknown'}",
                "artifact_type": "tool_result",
                "source": step.tool_name or "tool",
                "payload": step.tool_result,
            },
        )
    elif step.type == "answer" and step.content:
        AgentArtifact.objects.update_or_create(
            run=run,
            key="final-answer",
            defaults={
                **defaults,
                "title": "最终回答",
                "artifact_type": "answer",
                "source": "agent",
                "payload": step.content,
            },
        )
    elif step.type == "error" and step.content:
        AgentArtifact.objects.update_or_create(
            run=run,
            key=f"error-step-{step.id}",
            defaults={
                **defaults,
                "title": "运行错误",
                "artifact_type": "error",
                "source": "system",
                "payload": step.content,
            },
        )


def _emit_step(run, order, step_type, status="ok", **fields):
    step = AgentStep.objects.create(
        run=run,
        order=order,
        type=step_type,
        status=status,
        thought=fields.get("thought", ""),
        tool_name=fields.get("tool_name", ""),
        tool_args=fields.get("tool_args") or {},
        tool_result=fields.get("tool_result"),
        content=fields.get("content"),
    )
    _persist_step_artifact(step)

    AgentRun.objects.filter(id=run.id).update(step_count=order, updated_at=timezone.now())
    run.step_count = order

    event = {
        "step_id": step.id,
        "order": order,
        "type": step_type,
        "status": status,
    }
    event.update({
        key: value
        for key, value in fields.items()
        if key in {"thought", "tool_name", "tool_args", "tool_result", "content", "message"}
    })
    return event


def _run_is_cancelled(run: AgentRun):
    run.refresh_from_db(fields=["status", "updated_at", "completed_at", "step_count", "tools_used"])
    return run.status == "cancelled"


def run_agent_loop(run: AgentRun, hermes: HermesService, *, max_steps=None, verbose=False):
    del verbose

    max_steps = max_steps or run.max_steps or DEFAULT_MAX_STEPS
    update_count = run.update_status_atomic("running", started_at=timezone.now())
    run.refresh_from_db(fields=["status", "started_at", "updated_at", "step_count", "tools_used"])
    if not update_count and run.status == "cancelled":
        ensure_run_mission_artifact(run)
        yield _emit_step(
            run,
            order=1,
            step_type="error",
            status="skipped",
            content={"message": CANCELLED_NOTICE},
        )
        return
    ensure_run_mission_artifact(run)

    history = [{"role": "user", "content": run.task}]
    allowed_tool_names = _resolve_allowed_tool_names(run)
    native_tools = schemas.openai_tools(allowed_tool_names)
    tools_prompt_native = bool(native_tools)
    tools_prompt_text = schemas.prompt_tools_section(allowed_tool_names)
    memory_prompt, memory_records = _build_memory_prompt(run)
    file_prompt, attached_files = _build_file_prompt(run)
    _touch_memories(memory_records)

    yield _emit_step(
        run,
        order=1,
        step_type="plan",
        thought=f"Starting run with a maximum of {max_steps} steps.",
        content={
            "task": run.task,
            "memory_count": len(memory_records),
            "file_count": len(attached_files),
            "allowed_tools": allowed_tool_names,
            "file_ids": _dedupe_ids(run.file_ids),
        },
    )

    step_order = 2

    try:
        for _ in range(max_steps):
            if _run_is_cancelled(run):
                ensure_run_mission_artifact(run)
                yield _emit_step(
                    run,
                    order=step_order,
                    step_type="error",
                    status="skipped",
                    content={"message": CANCELLED_NOTICE},
                )
                return

            system_prompt = _build_system_prompt(
                run,
                "" if tools_prompt_native else tools_prompt_text,
                "\n\n".join(part for part in [memory_prompt, file_prompt] if part).strip(),
            )

            try:
                if tools_prompt_native:
                    response = hermes.chat_with_tools(
                        history,
                        tools=native_tools,
                        system_prompt=system_prompt,
                        tool_choice="auto",
                    )
                else:
                    response = hermes.chat_with_tools(history, tools=None, system_prompt=system_prompt)
                message = response.choices[0].message
            except Exception as exc:
                error_text = str(exc)
                if tools_prompt_native and ("tool" in error_text.lower() or "400" in error_text):
                    logger.info("Falling back to prompt-based tool calls for run %s: %s", run.id, exc)
                    tools_prompt_native = False
                    response = hermes.chat_with_tools(
                        history,
                        tools=None,
                        system_prompt=_build_system_prompt(run, tools_prompt_text, memory_prompt),
                    )
                    message = response.choices[0].message
                else:
                    raise

            tool_calls, assistant_text = parse_tool_calls(message)

            if _run_is_cancelled(run):
                ensure_run_mission_artifact(run)
                yield _emit_step(
                    run,
                    order=step_order,
                    step_type="error",
                    status="skipped",
                    content={"message": CANCELLED_NOTICE},
                )
                return

            if not tool_calls:
                final_answer = assistant_text or "The agent completed the run without a textual answer."
                history.append({"role": "assistant", "content": final_answer})
                yield _emit_step(
                    run,
                    order=step_order,
                    step_type="answer",
                    content={"answer": final_answer},
                )
                run.update_status_atomic(
                    "done",
                    answer=final_answer,
                    completed_at=timezone.now(),
                    tools_used=run.tools_used or [],
                )
                run.refresh_from_db(fields=["status", "answer", "completed_at", "tools_used", "step_count", "updated_at"])
                ensure_run_mission_artifact(run)
                return

            for tool_call in tool_calls:
                if _run_is_cancelled(run):
                    ensure_run_mission_artifact(run)
                    yield _emit_step(
                        run,
                        order=step_order,
                        step_type="error",
                        status="skipped",
                        content={"message": CANCELLED_NOTICE},
                    )
                    return

                name = tool_call["name"]
                args = tool_call.get("args") or {}
                thought = tool_call.get("thought") or ""

                yield _emit_step(
                    run,
                    order=step_order,
                    step_type="tool_call",
                    tool_name=name,
                    tool_args=args,
                    thought=thought,
                )
                step_order += 1

                if name not in allowed_tool_names:
                    result = {"ok": False, "error": f"Tool '{name}' is not enabled for this template."}
                else:
                    result = registry.execute_tool(name, args, {
                        "user": run.user,
                        "user_id": run.user_id,
                        "run_id": run.id,
                    })

                yield _emit_step(
                    run,
                    order=step_order,
                    step_type="tool_result",
                    tool_name=name,
                    tool_args=args,
                    tool_result=result,
                    status="ok" if result.get("ok") else "error",
                )
                step_order += 1

                tools_used = list(run.tools_used or [])
                if name not in tools_used:
                    tools_used.append(name)
                    AgentRun.objects.filter(id=run.id).update(tools_used=tools_used, updated_at=timezone.now())
                    run.tools_used = tools_used

                result_record = json.dumps(result, ensure_ascii=False)[:4000]
                if thought:
                    history.append({"role": "assistant", "content": thought})
                history.append({"role": "user", "content": f"Tool {name} result:\n{result_record}"})

        notice = f"Maximum step count reached ({max_steps}) before the agent produced a final answer."
        run.update_status_atomic("failed", error=notice, completed_at=timezone.now())
        run.refresh_from_db(fields=["status", "error", "completed_at", "step_count", "updated_at"])
        ensure_run_mission_artifact(run)
        yield _emit_step(
            run,
            order=step_order,
            step_type="error",
            status="error",
            content={"message": notice},
        )

    except Exception as exc:
        logger.exception("Agent run %s failed", run.id)
        run.update_status_atomic("failed", error=str(exc), completed_at=timezone.now())
        run.refresh_from_db(fields=["status", "error", "completed_at", "step_count", "updated_at"])
        ensure_run_mission_artifact(run)
        yield _emit_step(
            run,
            order=step_order,
            step_type="error",
            status="error",
            content={"message": str(exc)},
        )
