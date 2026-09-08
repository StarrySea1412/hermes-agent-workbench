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

# 中转站把模型思考链以 <think>/<thinking> 标签内嵌在正文里的模式
_THINK_CLOSED_RE = re.compile(r"<think(?:ing)?\s*>\s*(.*?)\s*</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_THINK_UNCLOSED_RE = re.compile(r"<think(?:ing)?\s*>\s*(.*)$", re.DOTALL | re.IGNORECASE)


def extract_reasoning(message) -> str:
    """读取中转站放在独立字段里的思考链（DeepSeek/OpenRouter 风格）。"""
    parts = []
    for attr in ("reasoning_content", "reasoning"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n\n".join(parts)


def split_think_tags(text: str) -> Tuple[str, str]:
    """把正文里内嵌的 <think>/<thinking> 段落抽出来。

    返回 (reasoning, cleaned_text)：正文同时保留未闭合标签的容错处理。
    """
    content = str(text or "")
    reasoning_parts = []

    def _collect(match):
        inner = match.group(1).strip()
        if inner:
            reasoning_parts.append(inner)
        return ""

    cleaned = _THINK_CLOSED_RE.sub(_collect, content)
    unclosed = _THINK_UNCLOSED_RE.search(cleaned)
    if unclosed and not cleaned[:unclosed.start()].strip().endswith(">"):
        inner = unclosed.group(1).strip()
        if inner:
            reasoning_parts.append(inner)
        cleaned = cleaned[: unclosed.start()]

    return "\n\n".join(reasoning_parts), cleaned.strip()


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
