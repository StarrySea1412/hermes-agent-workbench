import json
import logging
import tempfile

from django.db.models import Count
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.files.models import UploadedFile
from apps.files.validation import detect_file_type, validate_uploaded_file
from apps.projects.models import Conversation, Project, ProjectFile
from apps.projects.serializers import (
    ChatRequestSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    ProjectCreateSerializer,
    ProjectSerializer,
)
from services.ai_service import describe_ai_exception
from services.chat_service import ChatService
from services.export_service import generate_project_docx, generate_project_markdown

logger = logging.getLogger("api")
DEFAULT_CHAT_TITLE = "新对话"


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def projects(request):
    if request.method == "GET":
        queryset = Project.objects.filter(user=request.user).annotate(conversation_count=Count("conversations"))
        serializer = ProjectSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    serializer = ProjectCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    project = Project.objects.create(user=request.user, **serializer.validated_data)
    return Response(ProjectSerializer(project, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def project_detail(request, project_id):
    project = get_object_or_404(Project.objects.filter(user=request.user), id=project_id)

    if request.method == "GET":
        return Response(ProjectSerializer(project, context={"request": request}).data)

    if request.method == "PATCH":
        serializer = ProjectCreateSerializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProjectSerializer(project, context={"request": request}).data)

    project.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def project_files(request, project_id):
    project = get_object_or_404(Project.objects.filter(user=request.user), id=project_id)
    uploaded = []

    for file_obj in request.FILES.getlist("files"):
        validate_uploaded_file(file_obj)
        saved = UploadedFile.objects.create(
            user=request.user,
            file=file_obj,
            original_name=file_obj.name,
            file_type=detect_file_type(file_obj.name),
            file_size=file_obj.size,
            description=request.data.get("description", ""),
        )
        ProjectFile.objects.get_or_create(project=project, file=saved, defaults={"purpose": "reference"})
        uploaded.append(saved)

    file_ids = request.data.getlist("file_ids") if hasattr(request.data, "getlist") else request.data.get("file_ids", [])
    if isinstance(file_ids, (str, int)):
        file_ids = [file_ids]
    for file_id in file_ids:
        saved = get_object_or_404(UploadedFile.objects.filter(user=request.user), id=file_id)
        ProjectFile.objects.get_or_create(project=project, file=saved, defaults={"purpose": "reference"})
        uploaded.append(saved)

    return Response(ProjectSerializer(project, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def export_project_markdown(request, project_id):
    project = get_object_or_404(Project.objects.filter(user=request.user), id=project_id)
    content = generate_project_markdown(project)
    response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{project.title}.md"'
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def export_project_docx(request, project_id):
    project = get_object_or_404(Project.objects.filter(user=request.user), id=project_id)
    buffer = generate_project_docx(project)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    tmp.write(buffer.getvalue())
    tmp.close()
    response = FileResponse(
        open(tmp.name, "rb"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{project.title}.docx"'
    return response


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def conversations(request):
    if request.method == "GET":
        queryset = Conversation.objects.filter(user=request.user).select_related("project")
        serializer = ConversationSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    title = request.data.get("title") or DEFAULT_CHAT_TITLE
    mode = request.data.get("mode", "chat")
    project_id = request.data.get("project_id")
    project = None
    if project_id:
        project = get_object_or_404(Project.objects.filter(user=request.user), id=project_id)
    else:
        project = Project.objects.create(
            user=request.user,
            title=title,
            project_type="report" if mode == "report" else "presentation",
            description=request.data.get("description", ""),
        )
    conversation = Conversation.objects.create(user=request.user, project=project, title=title, mode=mode)
    return Response(ConversationDetailSerializer(conversation, context={"request": request}).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.filter(user=request.user).select_related("project"),
        id=conversation_id,
    )

    if request.method == "GET":
        return Response(ConversationDetailSerializer(conversation, context={"request": request}).data)

    if request.method == "PATCH":
        serializer = ConversationSerializer(conversation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(ConversationDetailSerializer(conversation, context={"request": request}).data)

    conversation.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def conversation_messages(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.filter(user=request.user), id=conversation_id)
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    service = ChatService(request.user)
    content = serializer.validated_data["content"]
    attachments = serializer.validated_data.get("attachments", [])
    service.save_user_message(conversation, content, attachment_ids=attachments)
    reply, metadata = service.generate_reply(conversation, content, attachment_ids=attachments)
    assistant_message = service.save_assistant_message(conversation, reply, metadata=metadata)
    service.sync_project_from_reply(conversation, reply)
    _refresh_conversation_title(conversation, content)

    return Response({
        "user_message_saved": True,
        "assistant": {
            "id": assistant_message.id,
            "role": assistant_message.role,
            "content": assistant_message.content,
            "metadata": assistant_message.metadata,
            "created_at": assistant_message.created_at,
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def conversation_stream(request, conversation_id):
    conversation = get_object_or_404(Conversation.objects.filter(user=request.user), id=conversation_id)
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    service = ChatService(request.user)
    content = serializer.validated_data["content"]
    attachments = serializer.validated_data.get("attachments", [])
    service.save_user_message(conversation, content, attachment_ids=attachments)
    _refresh_conversation_title(conversation, content)

    def event_stream():
        reply_parts = []
        interrupted = False
        # 中断保存路径需要本轮已累计的思考/工具事件：SSE 载荷里的 record dict
        # 会被后续 tool_result 就地改写，这里只持有引用即可看到最终状态
        turn_gateway = "hermes"
        turn_events = []
        turn_thoughts = []
        try:
            for event, data in service.stream_turn(conversation, content, attachment_ids=attachments):
                if event == "delta":
                    reply_parts.append(data.get("content", ""))
                elif event == "status":
                    turn_gateway = data.get("gateway") or turn_gateway
                elif event == "tool_call":
                    turn_events.append(data)
                elif event == "thought":
                    turn_thoughts.append(data)
                if event == "done":
                    reply = data.get("reply", "")
                    metadata = data.get("metadata", {})
                    assistant_message = service.save_assistant_message(conversation, reply, metadata=metadata)
                    agent_run_id = metadata.get("agent_run_id")
                    if agent_run_id:
                        try:
                            from apps.agents.models import AgentRun

                            AgentRun.objects.filter(
                                id=agent_run_id,
                                user=request.user,
                            ).update(message=assistant_message)
                        except Exception:
                            logger.exception(
                                "Failed to link AgentRun message: conversation_id=%s run_id=%s",
                                conversation.id,
                                agent_run_id,
                            )
                    service.sync_project_from_reply(conversation, reply)
                    payload = {
                        "message_id": assistant_message.id,
                        "reply": reply,
                        "metadata": {
                            **metadata,
                            "message_id": assistant_message.id,
                        },
                    }
                    yield _sse("done", payload)
                    continue
                yield _sse(event, data)
        except GeneratorExit:
            # 客户端断开（点了停止 / 关闭页面）：标记中断，保留已生成的部分回复
            interrupted = True
            raise
        except Exception as exc:
            logger.exception("Conversation stream failed: conversation_id=%s user_id=%s", conversation.id, request.user.id)
            diagnostic = describe_ai_exception(exc)
            yield _sse("error", {
                "message": diagnostic.get("message") or str(exc),
                "diagnostic": diagnostic,
            })
        finally:
            if interrupted:
                # 中断的聊天轮次：保存半截回复，并把关联运行标记为已取消（避免僵尸“运行中”）
                try:
                    from apps.agents.models import AgentRun

                    AgentRun.objects.filter(
                        user=request.user,
                        conversation=conversation,
                        source="chat_turn",
                        status__in=["pending", "running"],
                    ).update(status="cancelled", error="已由用户中断")
                except Exception:
                    logger.exception(
                        "Failed to cancel interrupted AgentRun: conversation_id=%s",
                        conversation.id,
                    )
                partial = "".join(reply_parts).strip()
                # 正文还没开始也算有内容：工具已执行时轨迹本身值得留痕，
                # 前端会以"没有收到可显示的回复"占位并渲染 tool_events
                if partial or turn_events or turn_thoughts:
                    try:
                        service.save_assistant_message(conversation, partial, metadata={
                            "gateway": turn_gateway,
                            "interrupted": True,
                            "mode": conversation.mode,
                            "thoughts": turn_thoughts,
                            "tool_events": turn_events,
                            "used_tools": sorted({e.get("name") for e in turn_events if e.get("name")}),
                        })
                    except Exception:
                        logger.exception(
                            "Failed to save interrupted reply: conversation_id=%s user_id=%s",
                            conversation.id,
                            request.user.id,
                        )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _refresh_conversation_title(conversation, content):
    if conversation.messages.count() > 1:
        return
    title = content.strip().splitlines()[0][:40] or conversation.title
    conversation.title = title
    if conversation.project and conversation.project.title == DEFAULT_CHAT_TITLE:
        conversation.project.title = title
        conversation.project.save(update_fields=["title", "updated_at"])
    conversation.save(update_fields=["title", "updated_at"])


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
