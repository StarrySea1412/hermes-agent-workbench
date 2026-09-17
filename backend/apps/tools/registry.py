"""Runtime registry for built-in agent tools."""

from apps.tools.handlers import doc_export, doc_parse, python_sandbox, web_search

TOOL_HANDLERS = {
    "doc_parse": doc_parse.handle,
    "doc_export": doc_export.handle,
    "web_search": web_search.handle,
    "python_sandbox": python_sandbox.handle,
}


def list_tool_names():
    return list(TOOL_HANDLERS.keys())


def get_handler(name):
    return TOOL_HANDLERS.get(name)


def execute_tool(name, args, context=None):
    """Execute a registered tool and return a structured result dict."""
    context = context or {}
    from services.tool_approval import resolve_binding, execute_approved, check_cancelled

    binding = resolve_binding(context)
    if binding:
        check_cancelled(context, binding)
        if name.startswith("mcp_"):
            return {"ok": False, "error": "审批模式暂不支持 MCP（包括发现和调用）。"}
    handler = get_handler(name)
    if binding and name == "python_sandbox":
        return execute_approved(name, args, context, handler, binding)
    if handler is None:
        if name.startswith("mcp_"):
            # MCP 动态工具：按前缀反查用户启用的服务器会话执行
            from services.mcp_client import call_user_tool

            user = (context or {}).get("user")
            if user is None:
                return {"ok": False, "error": f"MCP tool {name} requires an authenticated tool context."}
            return call_user_tool(user, name, args)
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return handler(args or {}, context or {})
    except Exception as exc:
        return {"ok": False, "error": f"Tool {name} failed: {exc}"}
