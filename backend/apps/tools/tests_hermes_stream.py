"""Hermes 网关 SSE 流解析与工具事件透传的回归测试。

网关把运行时整轮（含它自己的工具执行）聚合成一个 completion 流，
`event: hermes.tool.progress` 承载工具生命周期。这里验证：
1. SSE 解析出 reasoning/answer/tool_call/tool_result/final 事件序列
2. running→completed 共用同一个 record，状态就地更新
3. run_tool_loop 把流里的工具事件原样 emit 给 on_event
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from services.hermes_service import _iter_hermes_stream_events
from services.tool_loop import run_tool_loop


def _sse_lines():
    return [
        'data: {"choices":[{"delta":{"role":"assistant"}}]}',
        "",
        'data: {"choices":[{"delta":{"reasoning_content":"先想一下"}}]}',
        "",
        ": keepalive",
        "event: hermes.tool.progress",
        'data: {"tool":"web_search","toolCallId":"call-1","status":"running","label":"搜索 liquid glass"}',
        "",
        'data: {"choices":[{"delta":{"content":"部分"}}]}',
        'data: {"choices":[{"delta":{"content":"回答"}}]}',
        "",
        "event: hermes.tool.progress",
        'data: {"tool":"web_search","toolCallId":"call-1","status":"completed"}',
        "",
        "data: [DONE]",
    ]


class HermesSseParserTests(SimpleTestCase):
    def test_event_sequence(self):
        events = list(_iter_hermes_stream_events(_sse_lines()))
        kinds = [kind for kind, _ in events]
        self.assertEqual(
            kinds,
            ["reasoning", "tool_call", "answer", "answer", "tool_result", "final"],
        )

    def test_tool_record_is_shared_and_updated_in_place(self):
        events = list(_iter_hermes_stream_events(_sse_lines()))
        by_kind = {}
        for kind, payload in events:
            by_kind.setdefault(kind, []).append(payload)

        call_record = by_kind["tool_call"][0]
        result_record = by_kind["tool_result"][0]
        self.assertIs(call_record, result_record)
        self.assertEqual(call_record["name"], "web_search")
        self.assertEqual(call_record["id"], "call-1")
        self.assertEqual(call_record["status"], "ok")
        self.assertEqual(call_record["result_preview"], "搜索 liquid glass")
        self.assertEqual(by_kind["final"][0].content, "部分回答")

    def test_completed_without_seen_start_still_yields_result(self):
        lines = [
            "event: hermes.tool.progress",
            'data: {"tool":"file_write","toolCallId":"call-9","status":"completed"}',
            "data: [DONE]",
        ]
        events = list(_iter_hermes_stream_events(lines))
        kinds = [kind for kind, _ in events]
        self.assertEqual(kinds, ["tool_result", "final"])
        self.assertEqual(events[0][1]["name"], "file_write")

    def test_malformed_payload_is_skipped(self):
        lines = [
            "event: hermes.tool.progress",
            "data: not-json",
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]
        kinds = [kind for kind, _ in _iter_hermes_stream_events(lines)]
        self.assertEqual(kinds, ["answer", "final"])


class ToolLoopStreamToolEventTests(SimpleTestCase):
    def test_stream_tool_events_are_forwarded_to_on_event(self):
        seen = []

        def stream(*args, **kwargs):
            yield ("reasoning", "想一想")
            yield ("tool_call", {"id": "call-1", "name": "web_search", "args": {}, "thought": "", "status": "running"})
            yield ("tool_result", {"id": "call-1", "name": "web_search", "args": {}, "thought": "", "status": "ok", "result_preview": "完成"})
            yield ("answer", "最终答案")
            yield ("final", SimpleNamespace(content="最终答案"))

        agent = SimpleNamespace(stream_chat_with_tools=stream)
        result = run_tool_loop(
            agent=agent,
            history=[{"role": "user", "content": "hi"}],
            tool_names=[],
            build_system_prompt=lambda native, text: "sys",
            tool_context={},
            on_event=lambda kind, payload: seen.append((kind, payload)),
        )

        self.assertEqual(result.reply, "最终答案")
        kinds = [kind for kind, _ in seen]
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn(("tool_call", {"id": "call-1", "name": "web_search", "args": {}, "thought": "", "status": "running"}), seen)
        self.assertIn(("answer_delta", {"text": "最终答案"}), seen)
