import uuid

from django.conf import settings
from django.db import models


def args_default():
    return "[]"


def env_default():
    return "{}"


class McpServer(models.Model):
    """用户配置的 MCP stdio 服务器：命令行启动，工具按会话动态发现。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mcp_servers',
    )
    name = models.CharField('名称', max_length=64)
    command = models.CharField('启动命令', max_length=512)
    args = models.TextField('参数(JSON数组)', blank=True, default='[]')
    env = models.TextField('环境变量(JSON对象)', blank=True, default='{}')
    enabled = models.BooleanField('启用', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mcp_servers'
        ordering = ['created_at']
        unique_together = [('user', 'name')]
        verbose_name = 'MCP 服务器'
        verbose_name_plural = 'MCP 服务器'

    def __str__(self):
        return f"{self.user_id}:{self.name}"

    def clean_args(self):
        import json

        try:
            parsed = json.loads(self.args or '[]')
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    def clean_env(self):
        import json

        try:
            parsed = json.loads(self.env or '{}')
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


class ToolExecution(models.Model):
    """One immutable approval request; only the originating worker may claim it."""

    STATUS_CHOICES = [(value, value) for value in (
        "pending", "approved", "running", "succeeded", "failed",
        "denied", "expired", "cancelled",
    )]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey("projects.Conversation", on_delete=models.CASCADE, related_name="tool_executions")
    run = models.ForeignKey("agents.AgentRun", on_delete=models.CASCADE, related_name="tool_executions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tool_executions")
    tool_name = models.CharField(max_length=128)
    arguments = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    decision = models.CharField(max_length=5, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    error = models.TextField(blank=True, default="")
    result = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "tool_executions"
        ordering = ["created_at", "id"]


class WorkspaceWrite(models.Model):
    """One versioned workspace file write; the file content itself is the truth."""

    STATUS_CHOICES = [(value, value) for value in ("applied", "rejected", "rolled_back")]
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_writes")
    conversation = models.ForeignKey(
        "projects.Conversation", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="workspace_writes")
    run = models.ForeignKey(
        "agents.AgentRun", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="workspace_writes")
    path = models.CharField(max_length=512)
    previous = models.TextField(null=True, blank=True)
    proposed = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="applied", db_index=True)
    applied = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workspace_writes"
        ordering = ["-created_at", "id"]
