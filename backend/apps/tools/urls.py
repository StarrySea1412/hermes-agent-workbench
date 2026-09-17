from django.urls import path

from apps.tools import approval_views, mcp_views

urlpatterns = [
    path("tool-executions/", approval_views.tool_executions),
    path("tool-executions/<uuid:execution_id>/decision/", approval_views.tool_execution_decision),
    path("workspace-writes/", approval_views.workspace_writes),
    path("workspace-writes/<int:write_id>/rollback/", approval_views.workspace_write_rollback),
    path("mcp-servers", mcp_views.mcp_servers),
    path("mcp-servers/<int:server_id>", mcp_views.mcp_server_detail),
    path("mcp-servers/<int:server_id>/probe", mcp_views.mcp_server_probe),
]
