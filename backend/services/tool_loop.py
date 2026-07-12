"""Shared multi-turn tool-calling loop used by chat and agent runs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from apps.tools import registry, schemas
from services.tool_call_parser import parse_tool_calls

logger = logging.getLogger("api")

DEFAULT_MAX_TURNS = 8


@dataclass
class ToolLoopResult:
    reply: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    tool_events: List[Dict[str, Any]] = field(default_factory=list)
    used_tools: List[str] = field(default_factory=list)
    thoughts: List[Dict[str, str]] = field(default_factory=list)
    turns: int = 0
    exhausted: bool = False


def summarize_tool_result(result):
    if not isinstance(result, dict):
        return str(result)[:180]
    if not result.get("ok"):
        return str(result.get("error") or "工具执行失败。")[:180]

    payload = result.get("result")
    if isinstance(payload, dict):
        if "filename" in payload and "text" in payload:
            return f"已读取 {payload.get('filename')}，返回 {len(payload.get('text') or '')} 个字符。"
        if "results" in payload:
            return f"已返回 {len(payload.get('results') or [])} 条搜索结果。"
        if "filename" in payload and "url" in payload:
            return f"已导出 {payload.get('filename')}。"
    return json.dumps(payload, ensure_ascii=False)[:180] if payload is not None else "工具执行完成。"


def run_tool_loop(
    *,
    agent,
    history: List[Dict[str, Any]],
    tool_names: Iterable[str],
    build_system_prompt: Callable[[bool, str], str],
    tool_context: Dict[str, Any],
    max_turns: int = DEFAULT_MAX_TURNS,
    extra_headers: Optional[Dict[str, str]] = None,
    on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ToolLoopResult:
    """Run a native/prompt tool loop until a final assistant answer or max turns.

    build_system_prompt(native_tools_enabled, tools_prompt_text) -> system prompt string
    on_event(event_type, payload) is optional; event types: status, thought, tool_call, tool_result
    """
    allowed = list(tool_names or [])
    native_tools = schemas.openai_tools(allowed)
    tools_prompt_native = bool(native_tools)
    tools_prompt_text = schemas.prompt_tools_section(allowed)
    history = list(history)
    result = ToolLoopResult(history=history)

    def emit(event_type: str, payload: Dict[str, Any]):
        if on_event:
            on_event(event_type, payload)

    for turn_index in range(max_turns):
        if should_cancel and should_cancel():
            result.exhausted = False
            return result

        result.turns = turn_index + 1
        system_prompt = build_system_prompt(tools_prompt_native, tools_prompt_text)

        try:
            response = agent.chat_with_tools(
                history,
                tools=native_tools if tools_prompt_native else None,
                system_prompt=system_prompt,
                tool_choice="auto",
                extra_headers=extra_headers,
            )
            message = response.choices[0].message
        except TypeError:
            # Some agents do not accept extra_headers
            response = agent.chat_with_tools(
                history,
                tools=native_tools if tools_prompt_native else None,
                system_prompt=system_prompt,
                tool_choice="auto",
            )
            message = response.choices[0].message
        except Exception as exc:
            error_text = str(exc)
            if tools_prompt_native and ("tool" in error_text.lower() or "400" in error_text):
                logger.info("Falling back to prompt-based tool calls: %s", exc)
                tools_prompt_native = False
                emit("status", {
                    "stage": "tool_fallback",
                    "message": "当前模型不接受原生 tools，已切到提示词式工具调用。",
                })
                continue
            raise

        tool_calls, assistant_text = parse_tool_calls(message)
        if not tool_calls:
            result.reply = assistant_text or ""
            if result.reply:
                history.append({"role": "assistant", "content": result.reply})
            return result

        for tool_index, tool_call in enumerate(tool_calls, start=1):
            if should_cancel and should_cancel():
                return result

            name = tool_call.get("name") or ""
            args = tool_call.get("args") or {}
            thought_text = (tool_call.get("thought") or "").strip()
            call_id = f"turn-{turn_index + 1}-tool-{tool_index}"
            event_record = {
                "id": call_id,
                "name": name,
                "args": args,
                "thought": thought_text,
                "status": "running",
            }
            result.tool_events.append(event_record)

            if thought_text:
                thought = {"title": f"准备调用 {name}", "content": thought_text}
                result.thoughts.append(thought)
                emit("thought", thought)

            emit("tool_call", event_record)

            if name not in allowed:
                tool_result = {"ok": False, "error": f"Tool '{name}' is not enabled."}
            else:
                tool_result = registry.execute_tool(name, args, tool_context)

            event_record["status"] = "ok" if tool_result.get("ok") else "error"
            event_record["result"] = tool_result
            event_record["result_preview"] = summarize_tool_result(tool_result)
            emit("tool_result", event_record)

            if name and name not in result.used_tools:
                result.used_tools.append(name)

            result_record = json.dumps(tool_result, ensure_ascii=False)[:4000]
            if thought_text:
                history.append({"role": "assistant", "content": thought_text})
            if tool_index == 1 and assistant_text and assistant_text.strip():
                history.append({"role": "assistant", "content": assistant_text.strip()[:1500]})
            history.append({"role": "user", "content": f"Tool {name} result:\n{result_record}"})

    result.exhausted = True
    return result
