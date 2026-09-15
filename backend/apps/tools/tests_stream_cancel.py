"""流内取消的回归测试。

取消检查原本只在轮次/工具边界（思考轮可阻塞 180s+ 不可打断）；
现在 _consume_stream_turn 逐事件检查 should_cancel，命中即 break 生成器，
GeneratorExit 沿生成器传播关掉上游 HTTP 连接。
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from services.tool_loop import run_tool_loop


class FakeStreamingAgent:
    """持续产出思考增量的流式 agent；记录生成器是否被提前关闭。"""

    def __init__(self, total_events=50):
        self.total_events = total_events
        self.closed = False

    def stream_chat_with_tools(self, messages, **kwargs):
        try:
            for i in range(self.total_events):
                yield "reasoning", f"chunk-{i} "
        finally:
            self.closed = True


class CompletingStreamingAgent:
    def __init__(self):
        self.closed = False

    def stream_chat_with_tools(self, messages, **kwargs):
        try:
            yield "reasoning", "想一想"
            yield "answer", "你好"
            yield "final", SimpleNamespace(content="你好")
        finally:
            self.closed = True


class StreamCancelTests(SimpleTestCase):
    def test_cancel_inside_stream_closes_upstream_and_returns_empty_reply(self):
        agent = FakeStreamingAgent()
        seen = {"deltas": 0}

        def should_cancel():
            # 第 5 个增量后置位，模拟用户在思考流中途点停止
            return seen["deltas"] >= 5

        def on_event(kind, payload):
            if kind == "thought_delta":
                seen["deltas"] += 1

        result = run_tool_loop(
            agent=agent,
            history=[{"role": "user", "content": "hi"}],
            tool_names=[],
            build_system_prompt=lambda *args: "",
            tool_context={},
            max_turns=5,
            on_event=on_event,
            should_cancel=should_cancel,
        )

        # break 必须真的关掉生成器（等价于掐断上游连接）
        self.assertTrue(agent.closed)
        self.assertFalse(result.exhausted)
        self.assertEqual(result.reply, "")
        self.assertEqual(result.turns, 1)

    def test_stream_completes_normally_without_cancel(self):
        agent = CompletingStreamingAgent()

        result = run_tool_loop(
            agent=agent,
            history=[{"role": "user", "content": "hi"}],
            tool_names=[],
            build_system_prompt=lambda *args: "",
            tool_context={},
            max_turns=3,
        )

        self.assertEqual(result.reply, "你好")
        self.assertFalse(result.exhausted)
        self.assertTrue(agent.closed)
