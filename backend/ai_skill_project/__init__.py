"""Hermes 项目包 — 导入 Celery app，确保 Django 启动时被注册"""
from .celery import app as celery_app

__all__ = ("celery_app",)
