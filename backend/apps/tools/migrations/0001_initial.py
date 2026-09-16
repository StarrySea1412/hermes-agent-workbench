from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='McpServer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64, verbose_name='名称')),
                ('command', models.CharField(max_length=512, verbose_name='启动命令')),
                ('args', models.TextField(blank=True, default='[]', verbose_name='参数(JSON数组)')),
                ('env', models.TextField(blank=True, default='{}', verbose_name='环境变量(JSON对象)')),
                ('enabled', models.BooleanField(default=True, verbose_name='启用')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mcp_servers', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'mcp_servers',
                'ordering': ['created_at'],
                'unique_together': {('user', 'name')},
                'verbose_name': 'MCP 服务器',
                'verbose_name_plural': 'MCP 服务器',
            },
        ),
    ]
