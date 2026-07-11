"""Celery 应用配置

通过环境变量 CELERY_BROKER_URL / CELERY_RESULT_BACKEND 配置，
默认指向本地 Redis（Docker 部署时由 docker-compose 注入 redis 服务地址）。
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_skill_project.settings")

app = Celery("ai_skill")

# 从 Django settings 读取 CELERY_* 前缀配置
app.config_from_object("django.conf:settings", namespace="CELERY")

# 自动发现任务：会扫描 apps/*/tasks.py
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
