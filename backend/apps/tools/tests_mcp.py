"""MCP 客户端的回归测试。

用一个真实的最小 MCP echo 服务器子进程（stdin/stdout JSON-RPC）验证：
握手、tools/list、工具名前缀、registry 动态分发、管理 API。
"""
import json
import sys
import tempfile
import os

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tools import registry
from apps.tools.models import McpServer
from services import mcp_client
from services.mcp_client import McpStdioSession, mcp_tool_name, sanitize_name_part, to_openai_tool

ECHO_SERVER = """\
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        resp = {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "echo", "version": "1"}}}
    elif method == "tools/list":
        resp = {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo", "description": "回显输入", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
            {"name": "ping", "description": "返回 pong", "inputSchema": {"type": "object", "properties": {}}},
        ]}}
    elif method == "tools/call":
        args = (msg.get("params") or {}).get("arguments") or {}
        resp = {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"echo: {args.get('text', '')}"}], "isError": False}}
    else:
        if mid is None:
            continue
        resp = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""


class NamingTests(TestCase):
    def test_prefix_and_sanitization(self):
        self.assertEqual(mcp_tool_name("我的 fs", "read file"), "mcp____fs_read_file")
        self.assertEqual(sanitize_name_part("a b/c"), "a_b_c")

    def test_name_length_capped(self):
        name = mcp_tool_name("very-long-server-name-that-goes-on", "another-extremely-long-tool-name")
        self.assertLessEqual(len(name), 64)

    def test_openai_tool_conversion(self):
        converted = to_openai_tool({
            "prefixed": "mcp_fs_read", "description": "读取", "input_schema": {"type": "object"},
        })
        self.assertEqual(converted["type"], "function")
        self.assertEqual(converted["function"]["name"], "mcp_fs_read")
        self.assertEqual(converted["function"]["parameters"], {"type": "object"})


class EchoServerRoundtripTests(TestCase):
    def setUp(self):
        mcp_client._sessions.clear()
        self.user = get_user_model().objects.create_user(username="mcp-user", password="x")
        fd, self.script = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(ECHO_SERVER)
        self.server = McpServer.objects.create(
            user=self.user,
            name="testsrv",
            command=sys.executable,
            args=json.dumps([self.script]),
        )

    def tearDown(self):
        mcp_client.shutdown_all()
        os.unlink(self.script)

    def test_discover_and_call_via_registry(self):
        tools = mcp_client.get_user_mcp_tools(self.user)
        prefixed = {tool["prefixed"] for tool in tools}
        self.assertIn("mcp_testsrv_echo", prefixed)
        self.assertIn("mcp_testsrv_ping", prefixed)

        result = registry.execute_tool(
            "mcp_testsrv_echo", {"text": "你好"}, {"user": self.user}
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["result"], "echo: 你好")

    def test_unknown_tool_returns_structured_error(self):
        result = registry.execute_tool("mcp_testsrv_nope", {}, {"user": self.user})
        self.assertFalse(result["ok"])
        self.assertIn("不可用", result["error"])

    def test_session_reused_and_invalidate_restarts(self):
        first = mcp_client.get_session(self.server)
        second = mcp_client.get_session(self.server)
        self.assertIs(first, second)

        mcp_client.invalidate_server(self.user.id, self.server.id)
        third = mcp_client.get_session(self.server)
        self.assertIsNot(first, third)

    def test_missing_user_context_rejected(self):
        result = registry.execute_tool("mcp_testsrv_echo", {"text": "x"}, {})
        self.assertFalse(result["ok"])
        self.assertIn("authenticated", result["error"])

    def test_openai_schema_end_to_end(self):
        tools = mcp_client.get_user_mcp_tools(self.user)
        converted = [to_openai_tool(tool) for tool in tools]
        self.assertTrue(all(item["function"]["name"].startswith("mcp_") for item in converted))


class McpServerApiTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient

        mcp_client._sessions.clear()
        self.user = get_user_model().objects.create_user(username="mcp-admin", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        mcp_client.shutdown_all()

    def test_create_list_delete(self):
        response = self.client.post("/api/mcp-servers", {
            "name": "fs", "command": "uvx", "args": ["mcp-server-fetch"], "env": {"DEBUG": "1"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        server_id = response.data["id"]

        listed = self.client.get("/api/mcp-servers")
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["args"], ["mcp-server-fetch"])

        patched = self.client.patch(f"/api/mcp-servers/{server_id}", {"enabled": False}, format="json")
        self.assertFalse(patched.data["enabled"])

        deleted = self.client.delete(f"/api/mcp-servers/{server_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(len(self.client.get("/api/mcp-servers").data), 0)

    def test_validation_errors(self):
        bad_args = self.client.post("/api/mcp-servers", {"name": "x", "command": "y", "args": "not-json"}, format="json")
        self.assertEqual(bad_args.status_code, 400)
        missing = self.client.post("/api/mcp-servers", {"name": "x"}, format="json")
        self.assertEqual(missing.status_code, 400)

    def test_probe_unreachable_server_fails_cleanly(self):
        response = self.client.post("/api/mcp-servers", {
            "name": "dead", "command": sys.executable, "args": ["-c", "import time; time.sleep(600)"],
        }, format="json")
        server_id = response.data["id"]
        probe = self.client.post(f"/api/mcp-servers/{server_id}/probe")
        self.assertFalse(probe.data["ok"])
        self.assertTrue(probe.data["error"])
