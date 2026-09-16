"""聊天回合取消：数据库注册表 + 短 TTL 进程内缓存。

Django dev server 是单进程多线程，原进程内字典就够；gunicorn 多 worker /
多机部署下 cancel 请求可能落在另一个进程，所以登记走数据库（Conversation
主键为键，天然按会话隔离）。检查路径高频（tool_loop 每事件/每边界一次），
用 0.5 秒 TTL 缓存挡住绝大部分 DB 查询——取消生效最多慢半秒，可接受。

SSE 生成器 finally 块负责清除登记，避免残留影响下一轮。
"""
from __future__ import annotations

import threading
import time


class TurnCancelled(Exception):
    """用户主动停止本轮生成——视图按中断处理，不当作错误。"""


_TTL = 0.5

_cache_lock = threading.Lock()
_cache: dict = {}  # conversation_id -> (负值=未取消, 时间戳)


def request_chat_cancel(conversation_id: int) -> bool:
    """标记该会话正在运行的回合应停止；返回是否登记成功。

    用 update_or_create 而不是 get_or_create + update，避免与 clear 并发时
    在多 worker 下丢标记。
    """
    from apps.projects.models import Conversation

    try:
        updated = Conversation.objects.filter(id=int(conversation_id)).update(cancel_requested=True)
        with _cache_lock:
            _cache[int(conversation_id)] = (updated > 0, time.monotonic())
        return updated > 0
    except Exception:
        # 取消登记失败不能炸掉 cancel API；检查端查不到标记只是多跑一轮
        return False


def is_chat_cancelled(conversation_id) -> bool:
    conversation_id = int(conversation_id)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(conversation_id)
    if cached and now - cached[1] < _TTL:
        return cached[0]
    value = _check_db(conversation_id)
    with _cache_lock:
        _cache[conversation_id] = (value, now)
    return value


def _check_db(conversation_id: int) -> bool:
    from apps.projects.models import Conversation

    try:
        return Conversation.objects.filter(
            id=conversation_id, cancel_requested=True
        ).exists()
    except Exception:
        # DB 抖动时宁可保守地报告"未取消"，别把正常回合错杀成中断
        return False


def clear_chat_cancel(conversation_id) -> None:
    conversation_id = int(conversation_id)
    from apps.projects.models import Conversation

    with _cache_lock:
        _cache.pop(conversation_id, None)
    try:
        Conversation.objects.filter(id=conversation_id).update(cancel_requested=False)
    except Exception:
        pass


def _reset_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
