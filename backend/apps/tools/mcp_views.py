"""MCP 服务器管理：增删改查、启停、连通性探测。"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.tools.models import McpServer
from services.mcp_client import invalidate_server

logger = logging.getLogger("api")

MAX_SERVERS_PER_USER = 12


def _serialize(server):
    return {
        "id": server.id,
        "name": server.name,
        "command": server.command,
        "args": server.clean_args(),
        "env": server.clean_env(),
        "enabled": server.enabled,
        "created_at": server.created_at,
    }


def _validate_payload(data, partial=False):
    fields = {}
    if "name" in data or not partial:
        name = str(data.get("name") or "").strip()
        if not name or len(name) > 64:
            return None, "名称必填且不超过 64 个字符。"
        fields["name"] = name
    if "command" in data or not partial:
        command = str(data.get("command") or "").strip()
        if not command or len(command) > 512:
            return None, "启动命令必填且不超过 512 个字符。"
        fields["command"] = command
    if "args" in data:
        try:
            parsed = data.get("args")
            if parsed is None or parsed == "":
                fields["args"] = "[]"
            else:
                import json

                parsed = json.loads(parsed) if isinstance(parsed, str) else parsed
                if not isinstance(parsed, list):
                    return None, "参数必须是 JSON 数组。"
                fields["args"] = json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return None, "参数必须是合法 JSON 数组。"
    if "env" in data:
        try:
            parsed = data.get("env")
            if parsed is None or parsed == "":
                fields["env"] = "{}"
            else:
                import json

                parsed = json.loads(parsed) if isinstance(parsed, str) else parsed
                if not isinstance(parsed, dict):
                    return None, "环境变量必须是 JSON 对象。"
                fields["env"] = json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return None, "环境变量必须是合法 JSON 对象。"
    if "enabled" in data:
        fields["enabled"] = bool(data.get("enabled"))
    return fields, ""


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def mcp_servers(request):
    if request.method == "GET":
        servers = McpServer.objects.filter(user=request.user)
        return Response([_serialize(server) for server in servers])

    if McpServer.objects.filter(user=request.user).count() >= MAX_SERVERS_PER_USER:
        return Response({"message": f"每个用户最多 {MAX_SERVERS_PER_USER} 个 MCP 服务器。"}, status=status.HTTP_400_BAD_REQUEST)

    fields, error = _validate_payload(request.data)
    if error:
        return Response({"message": error}, status=status.HTTP_400_BAD_REQUEST)
    if McpServer.objects.filter(user=request.user, name=fields["name"]).exists():
        return Response({"message": "同名 MCP 服务器已存在。"}, status=status.HTTP_400_BAD_REQUEST)

    server = McpServer.objects.create(user=request.user, **fields)
    return Response(_serialize(server), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def mcp_server_detail(request, server_id):
    try:
        server = McpServer.objects.get(id=server_id, user=request.user)
    except McpServer.DoesNotExist:
        return Response({"message": "MCP 服务器不存在。"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        invalidate_server(request.user.id, server.id)
        server.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    fields, error = _validate_payload(request.data, partial=True)
    if error:
        return Response({"message": error}, status=status.HTTP_400_BAD_REQUEST)
    for field, value in fields.items():
        setattr(server, field, value)
    server.save()
    # 配置变了，旧会话作废，下次调用按新配置重启
    invalidate_server(request.user.id, server.id)
    return Response(_serialize(server))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mcp_server_probe(request, server_id):
    """连通性探测：握手 + tools/list，返回发现的工具清单。"""
    import threading

    from services import mcp_client

    try:
        server = McpServer.objects.get(id=server_id, user=request.user)
    except McpServer.DoesNotExist:
        return Response({"message": "MCP 服务器不存在。"}, status=status.HTTP_404_NOT_FOUND)

    probe_result = {}

    def _run():
        try:
            session = mcp_client.get_session(server)
            tools = session.list_tools(refresh=True)
            probe_result["ok"] = True
            probe_result["tools"] = [
                {
                    "prefixed": mcp_client.mcp_tool_name(server.name, tool.get("name") or ""),
                    "name": tool.get("name"),
                    "description": tool.get("description") or "",
                }
                for tool in tools
            ]
        except Exception as exc:
            probe_result["ok"] = False
            probe_result["error"] = str(exc)
        finally:
            from django.db import connections

            connections.close_all()

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=45)
    if not probe_result:
        return Response({"ok": False, "error": "探测超时（45 秒），服务器未完成握手。"}, status=status.HTTP_504_GATEWAY_TIMEOUT)
    return Response(probe_result)
