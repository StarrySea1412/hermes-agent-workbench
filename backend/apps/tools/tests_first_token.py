"""首 token 看门狗的回归测试：超时中止、正常流不受影响、close 传播。"""
import time
from unittest import mock

from django.test import SimpleTestCase, override_settings

from services.ai_service import AIService


class FakeStream:
    """可编程延迟的假上游流：first_delay 卡首事件前，gap_delay 卡后续分片间。"""

    def __init__(self, items, first_delay=0.0, gap_delay=0.0):
        self.items = list(items)
        self.first_delay = first_delay
        self.gap_delay = gap_delay
        self.closed = False
        self._started = False

    def __iter__(self):
        return self

    def __next__(self):
        if not self.items:
            raise StopIteration
        item = self.items.pop(0)
        if self._started:
            time.sleep(self.gap_delay)
        else:
            self._started = True
            time.sleep(self.first_delay)
        return item

    def close(self):
        self.closed = True


class FirstTokenGuardTests(SimpleTestCase):
    def _service(self):
        return AIService.__new__(AIService)  # 跳过 __init__，只测守护方法

    @override_settings(AI_FIRST_TOKEN_TIMEOUT=1)
    def test_slow_first_token_aborts_with_actionable_error(self):
        stream = FakeStream([1, 2, 3], first_delay=2.5)
        with self.assertRaises(RuntimeError) as ctx:
            list(self._service()._first_token_guarded(stream))
        self.assertIn("首个流式事件", str(ctx.exception))
        self.assertTrue(stream.closed)

    @override_settings(AI_FIRST_TOKEN_TIMEOUT=1)
    def test_fast_first_slow_gap_passes(self):
        # 首事件快到，后续分片间隔长：看门狗不该管，read 超时管
        stream = FakeStream([1, 2, 3], gap_delay=1.8)
        collected = list(self._service()._first_token_guarded(stream))
        self.assertEqual(collected, [1, 2, 3])

    @override_settings(AI_FIRST_TOKEN_TIMEOUT=2)
    def test_upstream_error_propagates(self):
        class BrokenStream(FakeStream):
            def __next__(self):
                raise RuntimeError("upstream exploded")

        stream = BrokenStream([])
        with self.assertRaises(RuntimeError):
            list(self._service()._first_token_guarded(stream))

    @override_settings(AI_FIRST_TOKEN_TIMEOUT=2)
    def test_consumer_break_closes_stream(self):
        stream = FakeStream([1, 2, 3, 4, 5])
        for _ in self._service()._first_token_guarded(stream):
            break
        self.assertTrue(stream.closed)
