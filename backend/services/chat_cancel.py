"""聊天回合取消：进程内注册表 + 工具循环取消钩子。

Django 开发服务器单进程多线程，conversation_id → 事件就够；
SSE 生成器 finally 块负责注销，避免残留条目影响下一轮。
"""
from __future__ import annotations

import threading
from typing import Dict

class TurnCancelled(Exception):
    """用户主动停止本轮生成——视图按中断处理，不当作错误。"""


_lock = threading.Lock()
_cancelled: Dict[int, bool] = {}


def request_chat_cancel(conversation_id: int) -> bool:
    """标记该会话正在运行的回合应停止；返回是否登记成功。"""
    with _lock:
        _cancelled[int(conversation_id)] = True
    return True


def is_chat_cancelled(conversation_id) -> bool:
    with _lock:
        return _cancelled.get(int(conversation_id), False)


def clear_chat_cancel(conversation_id) -> None:
    with _lock:
        _cancelled.pop(int(conversation_id), None)
