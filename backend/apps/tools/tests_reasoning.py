"""思考链捕获与展示的回归测试。

覆盖中转站返回思考链的两种形态：
1. 独立字段 reasoning_content / reasoning（DeepSeek、OpenRouter 风格）
2. 正文内嵌 <think>/<thinking> 标签（含未闭合容错）
"""
from types import SimpleNamespace

from django.test import SimpleTestCase

from services.tool_call_parser import extract_reasoning, split_think_tags
from services.tool_loop import ToolLoopResult, run_tool_loop


class SplitThinkTagTests(SimpleTestCase):
    def test_closed_tag_is_extracted_and_stripped(self):
        reasoning, cleaned = split_think_tags("<think>先分析问题。</think>最终答案。")
        self.assertEqual(reasoning, "先分析问题。")
        self.assertEqual(cleaned, "最终答案。")

    def test_thinking_variant_and_multiline(self):
        reasoning, cleaned = split_think_tags("<thinking>\n第一行\n第二行\n</thinking>\n答案")
        self.assertIn("第一行", reasoning)
        self.assertIn("第二行", reasoning)
        self.assertEqual(cleaned, "答案")

    def test_unclosed_trailing_tag(self):
        reasoning, cleaned = split_think_tags("前置说明<think>还没想完")
        self.assertEqual(reasoning, "还没想完")
        self.assertEqual(cleaned, "前置说明")

    def test_multiple_tags_keep_order(self):
        reasoning, cleaned = split_think_tags("<think>A</think>中间<think>B</think>结尾")
        self.assertEqual(reasoning, "A\n\nB")
        self.assertEqual(cleaned, "中间结尾")

    def test_no_tags_returns_original(self):
        reasoning, cleaned = split_think_tags("普通回答，没有任何标签。")
        self.assertEqual(reasoning, "")
        self.assertEqual(cleaned, "普通回答，没有任何标签。")


class ExtractReasoningTests(SimpleTestCase):
    def test_reads_reasoning_content_field(self):
        message = SimpleNamespace(content="答案", reasoning_content="思考内容", reasoning=None)
        self.assertEqual(extract_reasoning(message), "思考内容")

    def test_reads_reasoning_field(self):
        message = SimpleNamespace(content="答案", reasoning="另一种字段")
        self.assertEqual(extract_reasoning(message), "另一种字段")

    def test_missing_fields_return_empty(self):
        self.assertEqual(extract_reasoning(SimpleNamespace(content="答案")), "")
        self.assertEqual(extract_reasoning(object()), "")


class ToolLoopReasoningTests(SimpleTestCase):
    def _run(self, message):
        agent = SimpleNamespace(
            chat_with_tools=lambda *args, **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=message)]
            )
        )
        events = []

        def build_system_prompt(native, text):
            return ""

        result = run_tool_loop(
            agent=agent,
            history=[{"role": "user", "content": "hi"}],
            tool_names=[],
            build_system_prompt=build_system_prompt,
            tool_context={},
            max_turns=3,
            on_event=lambda kind, payload: events.append((kind, payload)),
        )
        return result, events

    def test_reasoning_content_becomes_thought_event_and_clean_reply(self):
        message = SimpleNamespace(
            content="最终回答。",
            reasoning_content="我需要先理解用户意图。",
        )
        result, events = self._run(message)

        self.assertEqual(result.reply, "最终回答。")
        thoughts = [payload for kind, payload in events if kind == "thought"]
        self.assertTrue(any(item.get("source") == "model" for item in thoughts))
        self.assertIn("模型思考", thoughts[-1]["title"])

    def test_embedded_think_tag_is_split_out_of_reply(self):
        message = SimpleNamespace(content="<think>拆解需求。</think>这是结论。")
        result, events = self._run(message)

        self.assertEqual(result.reply, "这是结论。")
        thoughts = [payload for kind, payload in events if kind == "thought"]
        self.assertTrue(any("拆解需求" in item.get("content", "") for item in thoughts))
        self.assertTrue(all("<think>" not in item.get("content", "") for item in thoughts))

    def test_plain_reply_has_no_model_thought(self):
        result, events = self._run(SimpleNamespace(content="普通回答。"))
        self.assertEqual(result.reply, "普通回答。")
        self.assertFalse(any(item.get("source") == "model" for kind, payload in events if kind == "thought" for item in [payload]))


class ToolLoopThinkingBudgetTests(SimpleTestCase):
    """回归：推理型模型把输出预算耗尽在思考链上时（只有思考、没有正文），应放大 max_tokens 重试而不是返回空回复。"""

    def _run_stream_agent(self, turns):
        """turns: 每轮 (reasoning, answer) 的列表，第 N 次调用返回第 N 项。"""
        calls = []

        def stream(*args, **kwargs):
            calls.append(kwargs.get("max_tokens"))
            reasoning, answer = turns[min(len(calls) - 1, len(turns) - 1)]
            if reasoning:
                yield ("reasoning", reasoning)
            if answer:
                yield ("answer", answer)
            yield ("final", SimpleNamespace(content=answer, tool_calls=None))

        return SimpleNamespace(stream_chat_with_tools=stream), calls

    def _run(self, turns):
        agent, calls = self._run_stream_agent(turns)
        events = []
        result = run_tool_loop(
            agent=agent,
            history=[{"role": "user", "content": "hi"}],
            tool_names=[],
            build_system_prompt=lambda native, text: "",
            tool_context={},
            max_turns=4,
            on_event=lambda kind, payload: events.append((kind, payload)),
        )
        return result, calls, events

    def test_thought_only_turn_retries_with_larger_budget(self):
        result, calls, events = self._run([("只想答案，没写完就断了。", ""), ("", "最终答案。")])

        self.assertEqual(result.reply, "最终答案。")
        self.assertEqual(calls[0], None)  # 第一轮用 agent 默认预算
        self.assertEqual(calls[1], 8192)  # 重试放大到 8192
        statuses = [payload for kind, payload in events if kind == "status"]
        self.assertTrue(any("输出预算" in item.get("message", "") for item in statuses))

    def test_retry_twice_then_answer(self):
        result, calls, _ = self._run([("思考A", ""), ("思考B", ""), ("", "答案")])

        self.assertEqual(result.reply, "答案")
        self.assertEqual(calls, [None, 8192, 16384])

    def test_budget_ladder_gives_up_after_two_retries(self):
        result, calls, _ = self._run([("思考", "")])

        self.assertEqual(result.reply, "")
        self.assertEqual(calls, [None, 8192, 16384])
        self.assertFalse(result.exhausted)
