"""ToolCallParser — 双解析工具调用

兼容两种 function-calling 路径:
1. 原生 OpenAI tool_calls: ChatCompletionMessage.tool_calls 列表
   (当 Hermes gateway 吃 tools 参数时由 chat_with_tools 直接返回)。
2. 提示词式降级: 模型把工具调用写进正文一段 JSON
   `{"tool": "<name>", "args": {...}, "thought": "..."}` (常包在 ```json``` 围栏里)
   —— 当 gateway 不支持原生 tools 时用此路径。

对外只 exposes parse_tool_calls(message) -> (tool_calls_list, assistant_text):
- tool_calls_list: 统一成 [{"name", "args", "thought"}]; 空列表表示模型给出最终答案。
- assistant_text: 模型本轮正文 (用于把 thought/解释回灌历史, 也给前端展示)。
"""
import json
import re
from typing import List, Tuple

# 匹配 ```json ... ``` 围栏里的 JSON, 或行内 {"tool": ...} JSON 片段
_FENCED_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_RE = re.compile(r'\{\s*"tool"\s*:.*?\}', re.DOTALL)


def parse_tool_calls(message) -> Tuple[List[dict], str]:
    """message: OpenAI ChatCompletionMessage 对象 (有 .tool_calls 和 .content)。

    返回 (tool_calls, assistant_text)。
    tool_calls 元素: {"name": str, "args": dict, "thought": str}
    若有原生 tool_calls 则优先用之; 否则在正文里找 JSON 降级。
    """
    native = _parse_native(message)
    content = getattr(message, "content", "") or ""

    if native:
        return native, content

    fallback = _parse_prompt_json(content)
    if fallback:
        return fallback, content

    return [], content


def _parse_native(message) -> List[dict]:
    tool_calls = getattr(message, "tool_calls", None) or []
    parsed = []
    for tc in tool_calls:
        try:
            fn = tc.function
            args = json.loads(fn.arguments) if fn.arguments else {}
        except (AttributeError, json.JSONDecodeError, TypeError):
            continue
        parsed.append({
            "name": getattr(getattr(tc, "function", None), "name", "") or "",
            "args": args if isinstance(args, dict) else {},
            "thought": "",
            "id": getattr(tc, "id", ""),
            "native": True,
        })
    return parsed


def _parse_prompt_json(content: str) -> List[dict]:
    """从正文中抽出提示词式工具调用 JSON. 取第一个能解析成 {tool,...} 的。"""
    if not content:
        return []
    candidates = []
    for m in _FENCED_RE.finditer(content):
        candidates.append(m.group(1))
    for m in _BARE_RE.finditer(content):
        candidates.append(m.group(0))
    for raw in candidates:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or not obj.get("tool"):
            continue
        args = obj.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        return [{
            "name": str(obj["tool"]),
            "args": args,
            "thought": str(obj.get("thought") or ""),
            "id": "",
            "native": False,
        }]
    return []
