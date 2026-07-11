import json
import logging

from apps.ai_config.models import AIConfig
from apps.projects.models import Message
from apps.tools import registry, schemas
from services.ai_service import AIService, describe_ai_exception
from services.document_analyzer import DocumentAnalyzer
from services.hermes_service import build_session_id, create_hermes_service
from services.tool_call_parser import parse_tool_calls

logger = logging.getLogger("api")

CHAT_SYSTEM_PROMPT = """You are Hermes Chat running on Hermes Gateway.
Respond in Chinese when the user writes Chinese.

Your job is to produce usable work, not status narration. Prefer concrete deliverables:
- files, tables, checklists, plans, patches, summaries, or next actions;
- concise assumptions when data is missing;
- explicit limitations only when they affect the result.

Use tools when they improve correctness:
- If files are attached, inspect them with doc_parse before making claims.
- If fresh public information is required, call web_search. Do not claim web results unless the tool succeeded.
- If the user asks for Excel, XLSX, spreadsheet, CSV-like output, or a table file, call doc_export with format="xlsx".
- For user-facing file exports, use only provided tools such as doc_export. Do not ask for Python, shell, write_file, or execute_code permissions.

Output style:
- Put the answer or artifact link first.
- Use short headings and compact bullets.
- For tables, use Markdown tables.
- Do not explain internal implementation unless the user asks."""

MODE_INSTRUCTIONS = {
    "chat": "Treat this as an ongoing working session. Move the task forward and produce the most useful next artifact.",
    "deck": "When the user asks for slides, produce slide titles, bullets, notes, and export-ready structure.",
    "report": "When the user asks for a report, produce clear sections, evidence notes, and delivery-ready prose.",
}

MODE_TOOL_NAMES = {
    "chat": ["doc_parse", "web_search", "doc_export"],
    "deck": ["doc_parse", "web_search", "doc_export"],
    "report": ["doc_parse", "web_search", "doc_export"],
}

MAX_HERMES_TURNS = 6


class ChatService:
    def __init__(self, user):
        self.user = user

    def build_reasoning_trace(self, conversation, user_content, attachment_ids=None):
        session_id = self.get_session_id(conversation)
        files = self.get_context_files(conversation, attachment_ids=attachment_ids)
        tool_names = self.resolve_tool_names(conversation)
        mode_label = {
            "chat": "连续对话",
            "deck": "演示文稿",
            "report": "报告文档",
        }.get(conversation.mode, "交付物")
        project_title = conversation.project.title if conversation.project else conversation.title

        return [
            {
                "title": "接入 Hermes 会话",
                "content": f"当前会话绑定到 {session_id}，围绕“{project_title}”继续处理本轮请求。",
            },
            {
                "title": "装载上下文",
                "content": f"已装载 {len(files)} 份资料，并保留当前对话历史作为 Hermes 输入。",
            },
            {
                "title": "准备工具策略",
                "content": f"本轮允许 Hermes 按需调用 {', '.join(tool_names) if tool_names else '无工具'}，优先先取证再回答。",
            },
            {
                "title": "生成本轮结果",
                "content": f"按“{mode_label}”模式继续推进，并把回答整理成可继续编辑的输出。用户请求：{user_content[:120]}",
            },
        ]

    def build_context(self, conversation, attachment_ids=None):
        files = self.get_context_files(conversation, attachment_ids=attachment_ids)
        if not files:
            return ""
        return DocumentAnalyzer().summarize_for_context(files)

    def get_context_files(self, conversation, attachment_ids=None):
        files = []
        seen = set()

        if conversation.project_id:
            for link in conversation.project.project_files.select_related("file"):
                file_obj = link.file
                if not file_obj or file_obj.id in seen:
                    continue
                seen.add(file_obj.id)
                files.append(file_obj)

        if attachment_ids:
            for file_obj in self.user.uploaded_files.filter(id__in=attachment_ids):
                if file_obj.id in seen:
                    continue
                seen.add(file_obj.id)
                files.append(file_obj)

        return files

    def get_history(self, conversation, extra_user_message=None):
        messages = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages.order_by("created_at")
            if message.role in {"user", "assistant"}
        ]
        if extra_user_message:
            messages.append({"role": "user", "content": extra_user_message})
        return messages

    def get_session_id(self, conversation):
        if conversation.project_id:
            session_id = build_session_id(self.user.id, conversation.project_id)
            if session_id:
                return session_id
        return f"u{self.user.id}-c{conversation.id}"

    def resolve_tool_names(self, conversation):
        return MODE_TOOL_NAMES.get(conversation.mode, MODE_TOOL_NAMES["chat"])

    def generate_reply(self, conversation, user_content, attachment_ids=None):
        reply = ""
        metadata = {}
        for event, data in self.stream_turn(conversation, user_content, attachment_ids=attachment_ids):
            if event == "done":
                reply = data.get("reply", "")
                metadata = data.get("metadata", {})
        return reply, metadata

    def stream_turn(self, conversation, user_content, attachment_ids=None):
        session_id = self.get_session_id(conversation)
        files = self.get_context_files(conversation, attachment_ids=attachment_ids)
        base_history = self.get_history(conversation)
        tool_names = self.resolve_tool_names(conversation)
        tool_events = []
        used_tools = []
        thoughts = []

        yield "status", {
            "stage": "session_ready",
            "gateway": "hermes",
            "session_id": session_id,
            "mode": conversation.mode,
            "file_count": len(files),
            "tool_names": tool_names,
        }

        for thought in self.build_reasoning_trace(conversation, user_content, attachment_ids=attachment_ids):
            thoughts.append(thought)
            yield "thought", thought

        hermes = create_hermes_service(session_id=session_id)
        if hermes:
            try:
                yield from self._stream_agent_reply(
                    hermes,
                    conversation,
                    list(base_history),
                    files,
                    session_id,
                    tool_names,
                    thoughts,
                    tool_events,
                    used_tools,
                    gateway_label="hermes",
                )
                return
            except Exception as exc:
                logger.exception("Hermes chat turn failed: conversation_id=%s user_id=%s", conversation.id, self.user.id)
                diagnostic = describe_ai_exception(exc)
                yield "status", {
                    "stage": "compat_resume",
                    "gateway": "compat",
                    "session_id": session_id,
                    "message": f"Hermes 网关当前不可用，已切换到当前账号模型继续执行：{_format_runtime_error(exc)}",
                    "diagnostic": diagnostic,
                }

        compat = self._get_compat_agent()
        if compat:
            try:
                yield from self._stream_agent_reply(
                    compat,
                    conversation,
                    list(base_history),
                    files,
                    session_id,
                    tool_names,
                    thoughts,
                    tool_events,
                    used_tools,
                    gateway_label="compat",
                )
                return
            except Exception as exc:
                logger.exception("Compatible chat turn failed: conversation_id=%s user_id=%s", conversation.id, self.user.id)
                diagnostic = describe_ai_exception(exc)
                yield "status", {
                    "stage": "fallback",
                    "gateway": "fallback",
                    "session_id": session_id,
                    "message": f"当前账号模型也不可用，已回退到本地保底答复：{_format_runtime_error(exc)}",
                    "diagnostic": diagnostic,
                }

        reply = self._fallback_or_ai_reply(conversation, user_content, attachment_ids=attachment_ids, allow_ai=not compat)
        metadata = {
            **self.extract_delivery_metadata(reply),
            "gateway": "fallback",
            "session_id": session_id,
            "model_name": self._get_runtime_model_name(),
            "mode": conversation.mode,
            "thoughts": thoughts,
            "tool_events": tool_events,
            "used_tools": used_tools,
            "file_count": len(files),
        }
        for chunk in chunk_text(reply):
            yield "delta", {"content": chunk}
        yield "done", {"reply": reply, "metadata": metadata}

    def save_user_message(self, conversation, content, attachment_ids=None):
        metadata = {"attachments": attachment_ids or []}
        return Message.objects.create(conversation=conversation, role="user", content=content, metadata=metadata)

    def save_assistant_message(self, conversation, content, metadata=None):
        return Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=content,
            metadata=metadata or self.extract_delivery_metadata(content),
        )

    def extract_delivery_metadata(self, content):
        outline = []
        for line in (content or "").splitlines():
            stripped = line.strip(" -#\t")
            if not stripped:
                continue
            if "页" in stripped or "slide" in stripped.lower() or stripped[:2].isdigit():
                outline.append(stripped[:160])
        return {"outline": outline[:12]}

    def sync_project_from_reply(self, conversation, assistant_content):
        project = conversation.project
        if not project:
            return
        metadata = self.extract_delivery_metadata(assistant_content)
        outline = metadata.get("outline") or project.outline
        project.outline = outline
        project.final_content = assistant_content
        project.status = "writing"
        project.save(update_fields=["outline", "final_content", "status", "updated_at"])

    def _build_file_prompt(self, files):
        if not files:
            return ""

        lines = [
            "Attached files available in this conversation:",
        ]
        for file_obj in files[:8]:
            line = (
                f"- file_id={file_obj.id} | {file_obj.original_name} | "
                f"type={file_obj.file_type} | size={file_obj.file_size_display}"
            )
            if file_obj.description:
                line = f"{line} | note={file_obj.description[:120]}"
            lines.append(line)
        lines.append("Use doc_parse with a file_id when you need the real file contents.")
        return "\n".join(lines)

    def _build_system_prompt(self, conversation, file_prompt="", tools_prompt=""):
        project = conversation.project
        project_note = ""
        if project and project.description:
            project_note = f"Workspace note:\n{project.description[:1200]}"

        sections = [
            CHAT_SYSTEM_PROMPT,
            MODE_INSTRUCTIONS.get(conversation.mode, MODE_INSTRUCTIONS["chat"]),
            project_note,
            file_prompt,
            tools_prompt,
        ]
        return "\n\n".join(section for section in sections if section).strip()

    def _fallback_or_ai_reply(self, conversation, user_content, attachment_ids=None, allow_ai=True):
        context = self.build_context(conversation, attachment_ids=attachment_ids)
        messages = self.get_history(conversation)
        config = self._get_config()
        if not config or not allow_ai:
            return self._fallback_reply(conversation, user_content)
        return AIService(config).generate_content(messages, system_prompt=CHAT_SYSTEM_PROMPT, context=context)

    def _get_config(self):
        try:
            return AIConfig.objects.get(user=self.user, is_active=True)
        except AIConfig.DoesNotExist:
            return None

    def _get_runtime_model_name(self, agent=None):
        config = self._get_config()
        config_model = getattr(config, "model_name", "") if config else ""
        if config_model:
            return config_model
        return getattr(agent, "model", "") or ""

    def _fallback_reply(self, conversation, user_content):
        title = conversation.project.title if conversation.project else conversation.title
        session_id = self.get_session_id(conversation)
        files = self.get_context_files(conversation)
        tool_names = self.resolve_tool_names(conversation)
        return f"""Hermes 运行时这一轮暂时不可用，我先按当前会话状态把任务接住。

## 当前任务
{user_content[:500]}

## 当前上下文
1. 会话：{session_id}
2. 空间：{title}
3. 资料：{len(files)} 份
4. 工具：{", ".join(tool_names) if tool_names else "无"}

## 建议下一步
1. {("继续让我读取现有资料并提炼关键点。" if files else "先上传资料，或把目标、受众、截止时间补充清楚。")}
2. 明确你希望的输出形态：结论、方案、README、PRD、设计稿、汇报提纲都可以。
3. 我会继续按“理解 -> 证据 -> 结构 -> 下一步”的方式推进，而不是停在一次性回答。"""

    def _get_compat_agent(self):
        config = self._get_config()
        if not config:
            return None
        try:
            return AIService(config)
        except Exception as exc:
            logger.warning("Compatible AI service unavailable for user_id=%s: %s", self.user.id, exc)
            return None

    def _stream_agent_reply(
        self,
        agent,
        conversation,
        history,
        files,
        session_id,
        tool_names,
        thoughts,
        tool_events,
        used_tools,
        gateway_label,
    ):
        native_tools = schemas.openai_tools(tool_names)
        tools_prompt_native = bool(native_tools)
        tools_prompt_text = schemas.prompt_tools_section(tool_names)
        file_prompt = self._build_file_prompt(files)
        extra_headers = {"X-Hermes-Session-Id": session_id} if gateway_label == "compat" and session_id else None

        for turn_index in range(MAX_HERMES_TURNS):
            system_prompt = self._build_system_prompt(
                conversation,
                file_prompt,
                "" if tools_prompt_native else tools_prompt_text,
            )

            try:
                response = agent.chat_with_tools(
                    history,
                    tools=native_tools if tools_prompt_native else None,
                    system_prompt=system_prompt,
                    tool_choice="auto",
                    extra_headers=extra_headers,
                )
                message = response.choices[0].message
            except Exception as exc:
                error_text = str(exc)
                if tools_prompt_native and ("tool" in error_text.lower() or "400" in error_text):
                    logger.info("Falling back to prompt-based tool calls for conversation %s: %s", conversation.id, exc)
                    tools_prompt_native = False
                    yield "status", {
                        "stage": "tool_fallback",
                        "gateway": gateway_label,
                        "session_id": session_id,
                        "message": "当前模型不接受原生 tools，已切到提示词式工具调用。",
                    }
                    continue
                raise

            tool_calls, assistant_text = parse_tool_calls(message)
            if not tool_calls:
                if gateway_label == "hermes" and _looks_like_gateway_tool_block(assistant_text):
                    raise RuntimeError("Hermes gateway stopped on internal file-execution permissions.")
                reply = assistant_text or "Hermes 已完成本轮，但没有返回可显示文本。"
                metadata = {
                    **self.extract_delivery_metadata(reply),
                    "gateway": gateway_label,
                    "session_id": session_id,
                    "model_name": self._get_runtime_model_name(agent),
                    "mode": conversation.mode,
                    "thoughts": thoughts,
                    "tool_events": tool_events,
                    "used_tools": used_tools,
                    "file_count": len(files),
                }
                for chunk in chunk_text(reply):
                    yield "delta", {"content": chunk}
                yield "done", {"reply": reply, "metadata": metadata}
                return

            for tool_index, tool_call in enumerate(tool_calls, start=1):
                name = tool_call.get("name") or ""
                args = tool_call.get("args") or {}
                thought_text = (tool_call.get("thought") or "").strip()
                call_id = f"turn-{turn_index + 1}-tool-{tool_index}"
                event_record = {
                    "id": call_id,
                    "name": name,
                    "args": args,
                    "thought": thought_text,
                    "status": "running",
                }
                tool_events.append(event_record)

                if thought_text:
                    thought = {
                        "title": f"准备调用 {name}",
                        "content": thought_text,
                    }
                    thoughts.append(thought)
                    yield "thought", thought

                yield "tool_call", event_record

                if name not in tool_names:
                    result = {"ok": False, "error": f"Tool '{name}' is not enabled in Hermes Chat."}
                else:
                    result = registry.execute_tool(name, args, {
                        "user": self.user,
                        "user_id": self.user.id,
                        "project_id": conversation.project_id,
                        "conversation_id": conversation.id,
                    })

                event_record["status"] = "ok" if result.get("ok") else "error"
                event_record["result"] = result
                event_record["result_preview"] = summarize_tool_result(result)
                yield "tool_result", event_record

                if name and name not in used_tools:
                    used_tools.append(name)

                result_record = json.dumps(result, ensure_ascii=False)[:4000]
                if thought_text:
                    history.append({"role": "assistant", "content": thought_text})
                if tool_index == 1 and assistant_text and assistant_text.strip():
                    history.append({"role": "assistant", "content": assistant_text.strip()[:1500]})
                history.append({"role": "user", "content": f"Tool {name} result:\n{result_record}"})

        raise RuntimeError(f"Hermes 在 {MAX_HERMES_TURNS} 轮内没有产出最终回答。")


def chunk_text(text, size=24):
    text = text or ""
    for index in range(0, len(text), size):
        yield text[index:index + size]


def _looks_like_gateway_tool_block(text):
    content = (text or "").lower()
    if not content:
        return False
    permission_markers = [
        "permission",
        "execute_code",
        "write_file",
        "python",
        "权限",
        "写文件",
        "执行",
    ]
    deliverable_markers = ["xlsx", "excel", "文件", "导出"]
    return any(marker in content for marker in permission_markers) and any(
        marker in content for marker in deliverable_markers
    )


def _format_runtime_error(exc):
    details = describe_ai_exception(exc)
    message = details.get("message") or str(exc)
    error_type = details.get("error_type")
    hint = details.get("hint")
    parts = [message]
    if error_type:
        parts.append(f"类型：{error_type}")
    if hint:
        parts.append(f"建议：{hint}")
    return "；".join(parts)


def summarize_tool_result(result):
    if not isinstance(result, dict):
        return str(result)[:180]
    if not result.get("ok"):
        return str(result.get("error") or "工具执行失败。")[:180]

    payload = result.get("result")
    if isinstance(payload, dict):
        if "filename" in payload and "text" in payload:
            return f"已读取 {payload.get('filename')}，返回 {len(payload.get('text') or '')} 个字符。"
        if "results" in payload:
            return f"已返回 {len(payload.get('results') or [])} 条搜索结果。"
        if "filename" in payload and "url" in payload:
            return f"已导出 {payload.get('filename')}。"
    return json.dumps(payload, ensure_ascii=False)[:180] if payload is not None else "工具执行完成。"
