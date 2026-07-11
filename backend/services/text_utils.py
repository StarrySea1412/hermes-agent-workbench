"""
文本转换工具函数

共享的 Markdown → Canvas 编辑器格式转换逻辑，
供 AIService 和 HermesService 共同使用。
"""


def text_to_canvas_format(text: str) -> list:
    """
    将 Markdown 文本转换为 canvas 编辑器元素列表

    支持的格式：
    - # 一级标题
    - ## 二级标题
    - ### 三级标题
    - - 或 * 无序列表
    - 1. ~ 9. 有序列表
    - 普通段落

    Args:
        text: Markdown 格式文本

    Returns:
        canvas 编辑器元素列表
    """
    elements = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("# ") and not line.startswith("## "):
            elements.append({
                "type": "title",
                "level": "first",
                "children": [{"value": line[2:], "size": 26}],
            })
        elif line.startswith("## ") and not line.startswith("### "):
            elements.append({
                "type": "title",
                "level": "second",
                "children": [{"value": line[3:], "size": 24}],
            })
        elif line.startswith("### "):
            elements.append({
                "type": "title",
                "level": "third",
                "children": [{"value": line[4:], "size": 22}],
            })
        elif line.startswith("- ") or line.startswith("* "):
            elements.append({
                "type": "list",
                "listType": "bullet",
                "children": [{"value": line[2:]}],
            })
        elif line.startswith(tuple(f"{i}. " for i in range(1, 10))):
            elements.append({
                "type": "list",
                "listType": "number",
                "children": [{"value": line[3:]}],
            })
        else:
            elements.append({
                "type": "paragraph",
                "children": [{"value": line}],
            })

    return elements


def normalize_messages(messages):
    """规范化 LLM 消息列表: 只保留 user/assistant 角色、丢弃空内容。

    AIService 与 HermesService 之前各有一份相同实现, 现统一在此共享。
    """
    normalized = []
    for message in messages or []:
        role = message.get("role", "user")
        if role not in {"user", "assistant"}:
            role = "user"
        content = message.get("content", "")
        if content:
            normalized.append({"role": role, "content": content})
    return normalized
