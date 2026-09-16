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
