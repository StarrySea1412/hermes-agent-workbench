"""流式首事件看门狗：上游迟迟不吐第一个事件就中止本次尝试，交给降级链。

中转站常见故障形态是建立连接后长时间一字节不发；等 read 超时（240s/600s）
太浪费。首个事件一旦到达，后续分片间隔（模型思考）交回 read 超时管。
"""
from __future__ import annotations

import queue
import threading


def first_token_guarded(source, timeout, label="上游"):
    """包装任意可迭代源：timeout 秒内没有第一个元素就抛 RuntimeError。

    泵线程消费 source，全部事件经队列转发；生成器被 close（取消/降级）时
    通过 finally 关闭 source（如有 close 方法）。
    """
    events: queue.Queue = queue.Queue()
    END = object()

    def _pump():
        try:
            for item in source:
                events.put(item)
        except BaseException as exc:  # noqa: BLE001 - 原样转交主线程抛出
            events.put(exc)
        finally:
            events.put(END)

    threading.Thread(target=_pump, daemon=True).start()
    try:
        try:
            item = events.get(timeout=timeout)
        except queue.Empty:
            raise RuntimeError(
                f"{label} {timeout:g}s 未产出首个流式事件，已中止本次尝试"
                f"（可用环境变量 AI_FIRST_TOKEN_TIMEOUT 调整）"
            ) from None
        while True:
            if item is END:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
            item = events.get()
    finally:
        close = getattr(source, "close", None)
        if close:
            try:
                close()
            except Exception:
                pass
