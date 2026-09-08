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
