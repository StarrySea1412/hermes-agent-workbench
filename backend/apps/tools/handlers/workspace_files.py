"""Workspace file tool: read/list/write files under a per-user workspace root.

This is a controlled-mode convenience tool with per-call approval for writes —
not an isolation boundary. Paths must stay inside the user's workspace root.
"""
import difflib
import os
import tempfile
from pathlib import Path

from django.conf import settings

from apps.tools.models import WorkspaceWrite
from services.tool_approval import execute_approved, resolve_binding

MAX_TEXT_CHARS = 40000
MAX_WRITE_CHARS = 60000
MAX_LIST_ENTRIES = 200
IGNORED_NAMES = {"__pycache__", ".git", "node_modules", ".venv", "venv"}

META = {
    "source": "builtin",
    "runtime": "workspace",
    "notes": "Reads/lists/writes files only inside the requesting user's workspace directory. Writes require per-call approval in controlled mode; every write is versioned for accept/reject review.",
}

SCHEMA = {
    "name": "workspace_files",
    "description": (
        "Read, list, or write text files in the user's workspace. Actions: "
        "'read' {path}, 'list' {path?}, 'write' {path, content}. Paths are relative "
        "to the workspace root; traversal outside it is rejected. Writes are "
        "recorded with a unified diff and stay pending until the user accepts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["read", "list", "write"]},
            "path": {"type": "string", "description": "Relative path inside the workspace (empty for list root)."},
            "content": {"type": "string", "description": "Full new file content for 'write'."},
        },
        "required": ["action"],
    },
}


def workspace_root(user_id):
    root = getattr(settings, "WORKSPACE_ROOT", None)
    base = Path(root) if root else Path(tempfile.gettempdir()) / "ai-skill-workspaces"
    return base / str(user_id)


def _resolve(user_id, relative):
    root = workspace_root(user_id).resolve()
    candidate = (root / (relative or "")).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("路径越出工作区范围。")
    return root, candidate


def _relative_display(root, path):
    return str(path.relative_to(root)).replace("\\", "/")


def handle(args, context=None):
    action = (args or {}).get("action")
    if action not in ("read", "list", "write"):
        return {"ok": False, "error": "action 必须是 read/list/write。"}
    user = (context or {}).get("user")
    if user is None or getattr(user, "pk", None) is None:
        return {"ok": False, "error": "workspace_files 需要已认证的工具上下文。"}
    root, target = _resolve(user.pk, args.get("path"))
    if action == "list":
        return _list(root, target)
    if action == "read":
        return _read(root, target)
    return _write(args, context, root, target)


def _list(root, target):
    if not target.exists():
        return {"ok": False, "error": "目录不存在。"}
    if not target.is_dir():
        return {"ok": False, "error": "路径不是目录。"}
    entries = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: p.name)[:MAX_LIST_ENTRIES]:
            if entry.name in IGNORED_NAMES or entry.name.startswith("."):
                continue
            entries.append({"name": entry.name, "type": "dir" if entry.is_dir() else "file",
                            "size": entry.stat().st_size if entry.is_file() else None})
    except OSError as exc:
        return {"ok": False, "error": f"读取目录失败：{exc}"}
    return {"ok": True, "result": {"path": _relative_display(root, target) if target != root else "", "entries": entries}}


def _read(root, target):
    if not target.is_file():
        return {"ok": False, "error": "文件不存在。"}
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": f"读取文件失败：{exc}"}
    truncated = len(text) > MAX_TEXT_CHARS
    return {"ok": True, "result": {
        "path": _relative_display(root, target), "content": text[:MAX_TEXT_CHARS],
        "truncated": truncated,
    }}


def _write(args, context, root, target):
    content = args.get("content")
    if not isinstance(content, str):
        return {"ok": False, "error": "write 需要 content 字符串。"}
    if len(content) > MAX_WRITE_CHARS:
        return {"ok": False, "error": f"内容超过 {MAX_WRITE_CHARS} 字符上限。"}
    if target.is_dir():
        return {"ok": False, "error": "目标路径是目录。"}
    previous = ""
    if target.exists():
        if not target.is_file():
            return {"ok": False, "error": "目标路径不是普通文件。"}
        previous = target.read_text(encoding="utf-8", errors="replace")
    diff = "".join(difflib.unified_diff(
        previous.splitlines(keepends=True), content.splitlines(keepends=True),
        fromfile=f"a/{_relative_display(root, target)}", tofile=f"b/{_relative_display(root, target)}",
    ))
    if (context or {}).get("workspace_apply"):
        # 审批层以持久化参数重入本 handler：直接落版本行并写文件。
        return _apply_write(context, root, target, previous, content)
    if resolve_binding(context):
        # 受控模式：写入走审批闸门，批准后才以持久化参数重入 apply。
        return _approved_write(context, root, target, previous, content)
    # 非受控路径（旧行为兼容）：直接写入，不留待审记录。
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"写入文件失败：{exc}"}
    return {"ok": True, "result": {"path": _relative_display(root, target), "bytes": len(content.encode("utf-8")), "written": True}}


def _apply_write(context, root, target, previous, content):
    rel = _relative_display(root, target)
    version = WorkspaceWrite.objects.create(
        user_id=context.get("user_id"), conversation_id=context.get("conversation_id"),
        run_id=context.get("run_id"), path=rel,
        previous=previous if target.exists() else None,
        proposed=content, applied=False,
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        version.status = "rejected"
        version.error = f"写入文件失败：{exc}"
        version.save(update_fields=["status", "error", "updated_at"])
        return {"ok": False, "error": version.error, "write_id": version.pk}
    version.applied = True
    version.status = "applied"
    version.save(update_fields=["applied", "status", "updated_at"])
    diff = "".join(difflib.unified_diff(
        (previous or "").splitlines(keepends=True), content.splitlines(keepends=True),
        fromfile=f"a/{rel}", tofile=f"b/{rel}",
    ))
    return {"ok": True, "result": {
        "path": rel, "bytes": len(content.encode("utf-8")),
        "write_id": version.pk, "diff": diff,
        "note": "已应用。可在审批面板接受或回滚这次写入。",
    }}


def _approved_write(context, root, target, previous, content):
    rel = _relative_display(root, target)
    context = dict(context or {})
    context["workspace_apply"] = True

    def apply(arguments, _context):
        return _apply_write(_context, root, target, previous, arguments.get("content", ""))

    return execute_approved("workspace_files", {"action": "write", "path": rel, "content": content},
                            context, apply, resolve_binding(dict(context, workspace_apply=False)))
