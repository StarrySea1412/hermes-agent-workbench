"""Shared multi-turn tool-calling loop used by chat and agent runs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from apps.tools import registry, schemas
from services.tool_call_parser import extract_reasoning, parse_tool_calls, split_think_tags

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


def _consume_stream_turn(agent, history, tools, system_prompt, extra_headers, emit, turn_number, max_tokens=None):
    """消费中转站流式响应：思考链与正文逐字 emit，返回 (reasoning, answer, message)。"""
    reasoning_parts = []
    answer_parts = []
    message = None
    # 注意：首个参数必须按位置传——各 agent 实现的形参名不统一（messages/history），
    # 关键字传参会 TypeError
    call_args = [history]
    call_kwargs = {
        "tools": tools,
        "system_prompt": system_prompt,
        "tool_choice": "auto",
        "extra_headers": extra_headers,
    }
    if max_tokens is not None:
        call_kwargs["max_tokens"] = max_tokens
    for kind, payload in agent.stream_chat_with_tools(*call_args, **call_kwargs):
        if kind == "reasoning":
            reasoning_parts.append(payload)
            emit("thought_delta", {"text": payload, "turn": turn_number})
        elif kind == "answer":
            answer_parts.append(payload)
            emit("answer_delta", {"text": payload})
        elif kind in ("tool_call", "tool_result"):
            # 网关路径：工具由运行时在远端执行，生命周期事件从流里透传
            emit(kind, payload)
        elif kind == "final":
            message = payload
    return "".join(reasoning_parts), "".join(answer_parts), message


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
    # 推理型模型可能把输出预算全部花在思考链上（正文为空），
    # 此时空回答不直接落兜底文案，而是放大 max_tokens 重试，最多 2 档（8192 → 16384）。
    budget_step = 0

    def emit(event_type: str, payload: Dict[str, Any]):
        if on_event:
            on_event(event_type, payload)

    for turn_index in range(max_turns):
        if should_cancel and should_cancel():
            result.exhausted = False
            return result

        result.turns = turn_index + 1
        system_prompt = build_system_prompt(tools_prompt_native, tools_prompt_text)
        if budget_step:
            # 加大预算的同时纠正模型行为：只加 token 它会全部继续烧在思考上
            system_prompt += (
                "\n\n[系统提醒] 上一轮你只输出了思考过程，没有输出任何可见正文。"
                "请立即停止思考，把结论整理成最终回答的正文直接输出。"
            )
        use_stream = hasattr(agent, "stream_chat_with_tools")
        retry_budget = (8192, 16384)[budget_step - 1] if budget_step else None

        try:
            if use_stream:
                reasoning_text, answer_text, message = _consume_stream_turn(
                    agent,
                    history,
                    native_tools if tools_prompt_native else None,
                    system_prompt,
                    extra_headers,
                    emit,
                    turn_index + 1,
                    max_tokens=retry_budget,
                )
            else:
                response = agent.chat_with_tools(
                    history,
                    tools=native_tools if tools_prompt_native else None,
                    system_prompt=system_prompt,
                    tool_choice="auto",
                    extra_headers=extra_headers,
                    max_tokens=retry_budget,
                )
                message = response.choices[0].message
                reasoning_text, answer_text = "", ""
        except TypeError:
            # Some agents do not accept extra_headers or streaming kwargs
            response = agent.chat_with_tools(
                history,
                tools=native_tools if tools_prompt_native else None,
                system_prompt=system_prompt,
                tool_choice="auto",
            )
            message = response.choices[0].message
            use_stream = False
            reasoning_text, answer_text = "", ""
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

        # 中转站把模型思考链放在独立字段或 <think> 标签里，统一转成思考事件
        reasoning = reasoning_text or extract_reasoning(message)
        cleaned_text = answer_text if use_stream else (assistant_text or "")
        if not reasoning:
            embedded, cleaned_text = split_think_tags(cleaned_text)
            reasoning = embedded
        if reasoning:
            thought = {
                "title": f"模型思考（第 {turn_index + 1} 轮）",
                "content": reasoning,
                "source": "model",
                "streamed": bool(use_stream),
            }
            result.thoughts.append(thought)
            emit("thought", thought)

        if not tool_calls:
            cleaned = cleaned_text or ""
            if not cleaned and reasoning and budget_step < 2:
                # 只有思考没有正文：模型把输出预算耗尽在推理上，放大预算重试
                budget_step += 1
                emit("status", {
                    "stage": "thinking_budget",
                    "message": "模型思考占用了全部输出预算，正在加大输出上限重试。",
                })
                continue
            result.reply = cleaned
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
