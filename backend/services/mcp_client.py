"""MCP 客户端：stdio 服务器上的 JSON-RPC 2.0，工具按会话动态发现并注入 tool_loop。

- 每个启用的 (user, server) 一个常驻子进程；进程死亡下次调用自动重启
- 读超时用读取线程 + Queue（Windows 管道没有 select）
- 工具名加前缀 mcp_<server>_<tool> 进 OpenAI function 名空间；反查表按会话缓存
- 任何失败只降级（该服务器工具缺席），绝不阻断聊天
"""
from __future__ import annotations

import atexit
import itertools
import json
import logging
import os
import queue
import re
import subprocess
import threading

logger = logging.getLogger("api")

INITIALIZE_TIMEOUT = 30
LIST_TIMEOUT = 30
CALL_TIMEOUT = 90
MAX_TOOLS_PER_SERVER = 64
NAME_MAX = 64

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class McpError(RuntimeError):
    pass


def sanitize_name_part(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", str(value or "").strip())
    return cleaned[:24] or "srv"


def mcp_tool_name(server_name, tool_name):
    prefix = f"mcp_{sanitize_name_part(server_name)}_"
    room = NAME_MAX - len(prefix)
    return prefix + sanitize_name_part(tool_name)[:room]


def to_openai_tool(tool):
    """把 MCP tools/list 的条目转成 OpenAI function 定义。"""
    return {
        "type": "function",
        "function": {
            "name": tool["prefixed"],
            "description": tool.get("description") or f"MCP tool {tool.get('name')}",
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        },
    }


class McpStdioSession:
    """单个 MCP stdio 服务器会话：常驻子进程 + 请求/响应按 id 配对。"""

    def __init__(self, server):
        self.server = server
        self._proc = None
        self._writer_lock = threading.Lock()
        self._pending = {}
        self._ids = itertools.count(1)
        self._tools = None

    # -- 生命周期 -----------------------------------------------------------

    def _ensure_started(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        args = self.server.clean_args()
        env = os.environ.copy()
        env.update(self.server.clean_env())
        try:
            self._proc = subprocess.Popen(
                [self.server.command, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                env=env,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise McpError(f"无法启动 MCP 服务器 {self.server.name}: {exc}") from exc
        self._pending = {}
        self._tools = None
        threading.Thread(target=self._read_loop, daemon=True).start()
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ai-skill-workbench", "version": "1.0"},
            },
            timeout=INITIALIZE_TIMEOUT,
        )
        self._notify("notifications/initialized")

    def _read_loop(self):
        proc = self._proc
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message_id = message.get("id")
                if message_id is not None and ("result" in message or "error" in message):
                    waiter = self._pending.pop(message_id, None)
                    if waiter is not None:
                        waiter.put(message)
        except (ValueError, OSError):
            pass  # 进程退出/管道关闭：等下次调用重启

    def close(self):
        proc = self._proc
        self._proc = None
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    # -- JSON-RPC -----------------------------------------------------------

    def _send(self, payload):
        if self._proc is None or self._proc.poll() is not None:
            raise McpError(f"MCP 服务器 {self.server.name} 未运行")
        with self._writer_lock:
            try:
                self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except (OSError, ValueError) as exc:
                raise McpError(f"MCP 服务器 {self.server.name} 写入失败: {exc}") from exc

    def _request(self, method, params=None, timeout=CALL_TIMEOUT):
        self._ensure_started()
        message_id = next(self._ids)
        waiter = queue.Queue(maxsize=1)
        self._pending[message_id] = waiter
        self._send({"jsonrpc": "2.0", "id": message_id, "method": method, "params": params or {}})
        try:
            message = waiter.get(timeout=timeout)
        except queue.Empty:
            self._pending.pop(message_id, None)
            raise McpError(f"MCP 服务器 {self.server.name} 请求超时: {method}") from None
        if "error" in message:
            error = message["error"]
            raise McpError(f"MCP {method} 失败: {error.get('message') or error}")
        return message.get("result") or {}

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # -- MCP 语义 -----------------------------------------------------------

    def list_tools(self, refresh=False):
        if self._tools is not None and not refresh:
            return self._tools
        result = self._request("tools/list", timeout=LIST_TIMEOUT)
        tools = (result.get("tools") or [])[:MAX_TOOLS_PER_SERVER]
        self._tools = tools
        return tools

    def call_tool(self, tool_name, arguments):
        try:
            result = self._request(
                "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
                timeout=CALL_TIMEOUT,
            )
        except McpError as exc:
            # 未知工具多半是会话工具列表过期，刷新一次再试
            if "Unknown tool" not in str(exc):
                raise
            self.list_tools(refresh=True)
            result = self._request(
                "tools/call",
                {"name": tool_name, "arguments": arguments or {}},
                timeout=CALL_TIMEOUT,
            )

        content = result.get("content") or []
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                texts.append(str(item["text"]))
        text = "\n".join(texts).strip()
        structured = result.get("structuredContent")
        payload = structured if isinstance(structured, dict) and structured else (text or "工具执行完成，无文本输出。")
        return {
            "ok": not result.get("isError", False),
            "result": payload,
            "error": "" if not result.get("isError") else (text or "MCP 工具报告执行失败。"),
        }


# -- 会话池 ------------------------------------------------------------------

_sessions = {}
_pool_lock = threading.Lock()


def get_session(server):
    key = (server.user_id, server.id)
    with _pool_lock:
        session = _sessions.get(key)
        if session is None or session.server.command != server.command or session.server.args != server.args:
            if session is not None:
                session.close()
            session = McpStdioSession(server)
            _sessions[key] = session
        else:
            session.server = server
        return session


def invalidate_server(user_id, server_id):
    with _pool_lock:
        session = _sessions.pop((user_id, server_id), None)
    if session:
        session.close()


def shutdown_all():
    with _pool_lock:
        sessions = list(_sessions.values())
        _sessions.clear()
    for session in sessions:
        session.close()


atexit.register(shutdown_all)


# -- 面向 tool_loop 的接口 ----------------------------------------------------


def _enabled_servers(user):
    from apps.tools.models import McpServer

    return list(McpServer.objects.filter(user=user, enabled=True))


def get_user_mcp_tools(user):
    """收集该用户所有启用服务器的工具；单个服务器失败跳过不阻断。"""
    tools = []
    for server in _enabled_servers(user):
        try:
            session = get_session(server)
            for tool in session.list_tools():
                name = tool.get("name") or ""
                if not name:
                    continue
                tools.append({
                    "prefixed": mcp_tool_name(server.name, name),
                    "server_id": server.id,
                    "server_name": server.name,
                    "name": name,
                    "description": tool.get("description") or "",
                    "input_schema": tool.get("inputSchema") or {"type": "object", "properties": {}},
                })
        except Exception as exc:
            logger.warning("MCP tools/list failed for server %s: %s", server.name, exc)
    return tools


def call_user_tool(user, prefixed_name, arguments):
    """按前缀反查服务器并调用；找不到时返回结构化错误（工具循环按失败处理）。"""
    for server in _enabled_servers(user):
        try:
            session = get_session(server)
            for tool in session.list_tools():
                if mcp_tool_name(server.name, tool.get("name") or "") != prefixed_name:
                    continue
                return session.call_tool(tool["name"], arguments)
        except Exception as exc:
            logger.warning("MCP call failed on server %s for %s: %s", server.name, prefixed_name, exc)
    return {"ok": False, "error": f"MCP 工具 {prefixed_name} 不可用（服务器未响应或未启用）。"}
