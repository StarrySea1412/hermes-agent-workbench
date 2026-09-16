from django.urls import path

from apps.tools import mcp_views

urlpatterns = [
    path("mcp-servers", mcp_views.mcp_servers),
    path("mcp-servers/<int:server_id>", mcp_views.mcp_server_detail),
    path("mcp-servers/<int:server_id>/probe", mcp_views.mcp_server_probe),
]
