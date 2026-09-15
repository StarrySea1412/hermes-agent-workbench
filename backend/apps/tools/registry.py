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
    handler = get_handler(name)
    if handler is None:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return handler(args or {}, context or {})
    except Exception as exc:
        return {"ok": False, "error": f"Tool {name} failed: {exc}"}
