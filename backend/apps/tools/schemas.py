"""OpenAI tool schema export and UI-facing tool catalog helpers."""

from apps.tools import registry
from apps.tools.handlers.doc_export import META as DOC_EXPORT_META
from apps.tools.handlers.doc_export import SCHEMA as DOC_EXPORT_SCHEMA
from apps.tools.handlers.doc_parse import META as DOC_PARSE_META
from apps.tools.handlers.doc_parse import SCHEMA as DOC_PARSE_SCHEMA
from apps.tools.handlers.python_sandbox import META as PYTHON_SANDBOX_META
from apps.tools.handlers.python_sandbox import SCHEMA as PYTHON_SANDBOX_SCHEMA
from apps.tools.handlers.web_search import META as WEB_SEARCH_META
from apps.tools.handlers.web_search import SCHEMA as WEB_SEARCH_SCHEMA
from apps.tools.handlers.workspace_files import META as WORKSPACE_FILES_META
from apps.tools.handlers.workspace_files import SCHEMA as WORKSPACE_FILES_SCHEMA

TOOL_DESCRIPTORS = [
    {"schema": DOC_PARSE_SCHEMA, **DOC_PARSE_META},
    {"schema": DOC_EXPORT_SCHEMA, **DOC_EXPORT_META},
    {"schema": WEB_SEARCH_SCHEMA, **WEB_SEARCH_META},
    {"schema": PYTHON_SANDBOX_SCHEMA, **PYTHON_SANDBOX_META},
    {"schema": WORKSPACE_FILES_SCHEMA, **WORKSPACE_FILES_META},
]


def available_tool_names():
    return [item["schema"]["name"] for item in TOOL_DESCRIPTORS]


def _filter_descriptors(allowed_names=None):
    if not allowed_names:
        return TOOL_DESCRIPTORS
    allow_set = set(allowed_names)
    return [item for item in TOOL_DESCRIPTORS if item["schema"]["name"] in allow_set]


def openai_tools(allowed_names=None):
    """Return OpenAI-compatible tool definitions for the runtime."""
    items = []
    for descriptor in _filter_descriptors(allowed_names):
        schema = descriptor["schema"]
        items.append({
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"],
            },
        })
    return items


def prompt_tools_section(allowed_names=None):
    """Render a fallback text description of available tools for prompt mode."""
    descriptors = _filter_descriptors(allowed_names)
    if not descriptors:
        return ""

    lines = [
        "You may call tools when they improve accuracy or save work.",
        'When you need a tool, respond with JSON only, for example: {"tool": "<name>", "args": {...}, "thought": "..."}',
        "After the tool result is returned, continue the task and finish with a normal final answer when ready.",
        "",
        "Available tools:",
    ]

    for descriptor in descriptors:
        schema = descriptor["schema"]
        params = schema.get("parameters", {})
        required = set(params.get("required") or [])
        lines.append(f"- {schema['name']}: {schema['description']}")
        for param_name, spec in (params.get("properties") or {}).items():
            requirement = "required" if param_name in required else "optional"
            lines.append(
                f"  - {param_name} ({spec.get('type', 'any')}, {requirement}): {spec.get('description', '')}"
            )
    lines.append("")
    return "\n".join(lines)


def render_extra_tools_section(extra_tools):
    """动态工具（如 MCP）的提示词式描述，格式与 prompt_tools_section 一致。"""
    lines = []
    for tool in extra_tools or []:
        function = tool.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        params = function.get("parameters") or {}
        required = set(params.get("required") or [])
        lines.append(f"- {name}: {function.get('description') or ''}")
        for param_name, spec in (params.get("properties") or {}).items():
            requirement = "required" if param_name in required else "optional"
            spec_type = spec.get("type", "any") if isinstance(spec, dict) else "any"
            description = spec.get("description", "") if isinstance(spec, dict) else ""
            lines.append(f"  - {param_name} ({spec_type}, {requirement}): {description}")
    if not lines:
        return ""
    lines.append("")
    return "\n".join(lines)


def tool_catalog(enabled_names=None):
    """Return a UI-friendly list of tools and their registry status."""
    registered = set(registry.list_tool_names())
    enabled = set(enabled_names or [])
    items = []
    for descriptor in TOOL_DESCRIPTORS:
        schema = descriptor["schema"]
        name = schema["name"]
        items.append({
            "name": name,
            "description": schema["description"],
            "parameters": schema["parameters"],
            "registered": name in registered,
            "enabled": not enabled_names or name in enabled,
            "source": descriptor.get("source", "builtin"),
            "runtime": descriptor.get("runtime", "full"),
            "notes": descriptor.get("notes", ""),
        })
    return items
