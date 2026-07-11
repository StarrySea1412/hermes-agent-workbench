import os
import tempfile
from pathlib import Path

from django.db.models import F
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai_config.models import AIConfig
from apps.bids.models import Bid, BidChapter, BidStep
from apps.bids.serializers import (
    BidChapterCreateSerializer,
    BidChapterSerializer,
    BidChapterUpdateSerializer,
    BidCreateSerializer,
    BidDetailSerializer,
    BidOutlineSerializer,
    BidStepSerializer,
    BidStepUpdateSerializer,
    BidUpdateSerializer,
)
from apps.files.models import UploadedFile
from apps.files.validation import validate_uploaded_file


DEFAULT_STEPS = [
    {"order": 0, "label": "分析源资料", "status": "completed"},
    {"order": 1, "label": "生成大纲", "status": "completed"},
    {"order": 2, "label": "起草内容", "status": "completed"},
    {"order": 3, "label": "复核与润色", "status": "active"},
    {"order": 4, "label": "导出交付物", "status": "pending"},
]

DEFAULT_CHAPTERS = [
    {"title": "项目概述", "order": 0},
    {"title": "技术方案", "order": 1},
    {"title": "实施计划", "order": 2},
    {"title": "运维与支持", "order": 3},
    {"title": "培训与落地", "order": 4},
]


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def list_create_bids(request):
    if request.method == "GET":
        bids = Bid.objects.filter(user=request.user).order_by("-updated_at")
        serializer = BidOutlineSerializer(bids, many=True)
        return Response(serializer.data)

    serializer = BidCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    bid = Bid.objects.create(
        title=serializer.validated_data["title"],
        user=request.user,
    )

    for step_data in DEFAULT_STEPS:
        BidStep.objects.create(bid=bid, **step_data)

    for chapter_data in DEFAULT_CHAPTERS:
        BidChapter.objects.create(bid=bid, **chapter_data)

    bid.total_chapters = len(DEFAULT_CHAPTERS)
    bid.save()

    detail = BidDetailSerializer(bid)
    return Response(detail.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def bid_detail(request, bid_id):
    bid = _get_user_bid_or_404(request, bid_id)

    if request.method == "GET":
        serializer = BidDetailSerializer(bid)
        return Response(serializer.data)

    if request.method == "PATCH":
        serializer = BidUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "title" in serializer.validated_data:
            bid.title = serializer.validated_data["title"]
        if "status" in serializer.validated_data:
            bid.status = serializer.validated_data["status"]
        bid.save()
        return Response(BidDetailSerializer(bid).data)

    BidChapter.objects.filter(bid=bid).delete()
    BidStep.objects.filter(bid=bid).delete()
    bid.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def bid_steps(request, bid_id):
    bid = _get_user_bid_or_404(request, bid_id)
    steps = bid.steps.order_by("order")
    serializer = BidStepSerializer(steps, many=True)
    return Response(serializer.data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_bid_step(request, bid_id, step_id):
    bid = _get_user_bid_or_404(request, bid_id)
    step = get_object_or_404(bid.steps, id=step_id)
    serializer = BidStepUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    step.status = serializer.validated_data["status"]
    step.save()
    return Response(BidStepSerializer(step).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def bid_chapters(request, bid_id):
    bid = _get_user_bid_or_404(request, bid_id)
    if request.method == "GET":
        chapters = bid.chapters.filter(parent__isnull=True).order_by("order")
        serializer = BidChapterSerializer(chapters, many=True)
        return Response(serializer.data)

    serializer = BidChapterCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    parent = None
    parent_id = serializer.validated_data.get("parent_id")
    if parent_id is not None:
        parent = get_object_or_404(bid.chapters, id=parent_id)

    chapter = BidChapter.objects.create(
        bid=bid,
        parent=parent,
        title=serializer.validated_data["title"],
        order=serializer.validated_data.get("order", 0),
        content=serializer.validated_data.get("content"),
    )

    if parent is None:
        Bid.objects.filter(id=bid.id).update(total_chapters=F("total_chapters") + 1)

    return Response(BidChapterSerializer(chapter).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def chapter_detail(request, bid_id, chapter_id):
    bid = _get_user_bid_or_404(request, bid_id)
    chapter = get_object_or_404(bid.chapters, id=chapter_id)

    if request.method == "GET":
        serializer = BidChapterSerializer(chapter)
        return Response(serializer.data)

    if request.method == "PATCH":
        serializer = BidChapterUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if "title" in serializer.validated_data:
            chapter.title = serializer.validated_data["title"]
        if "order" in serializer.validated_data:
            chapter.order = serializer.validated_data["order"]
        if "content" in serializer.validated_data:
            chapter.content = serializer.validated_data["content"]
        chapter.save()
        return Response(BidChapterSerializer(chapter).data)

    was_top_level = chapter.parent_id is None
    BidChapter.objects.filter(parent=chapter).delete()
    chapter.delete()
    if was_top_level:
        Bid.objects.filter(id=bid.id, total_chapters__gt=0).update(total_chapters=F("total_chapters") - 1)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def export_bid(request, bid_id):
    bid = _get_user_bid_or_404(request, bid_id)
    chapters = bid.chapters.filter(parent__isnull=True).order_by("order")

    chapter_list = []
    for chapter in chapters:
        chapter.children_list = list(BidChapter.objects.filter(parent=chapter).order_by("order"))
        chapter_list.append(chapter)

    from services.export_service import generate_bid_document

    buffer = generate_bid_document(bid, chapter_list)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    tmp.write(buffer.getvalue())
    tmp.close()

    response = FileResponse(
        open(tmp.name, "rb"),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{bid.title}.docx"'

    import threading

    def cleanup():
        import time

        time.sleep(5)
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    threading.Thread(target=cleanup, daemon=True).start()

    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def analyze_bid_document(request):
    if request.data.get("file_path"):
        return Response(
            {"message": "出于安全原因，已不再支持 file_path。请改为上传文件或提供 file_id。"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    config = _get_user_ai_config(request.user)
    if isinstance(config, Response):
        return config

    cleanup_path = None
    file_path = None
    uploaded_file = request.FILES.get("file")
    if uploaded_file:
        file_path, cleanup_path = _write_temp_upload(uploaded_file)
    else:
        file_id = request.data.get("file_id")
        if not file_id:
            return Response({"message": "请上传文件或提供 file_id。"}, status=status.HTTP_400_BAD_REQUEST)
        saved_file = get_object_or_404(UploadedFile.objects.filter(user=request.user), id=file_id)
        file_path = saved_file.file.path

    from services.bid_analyzer import BidAnalyzer

    analyzer = BidAnalyzer(config)
    try:
        result = analyzer.analyze(file_path)
        return Response(
            {
                "success": True,
                "project_name": result.get("project_name"),
                "project_number": result.get("project_number"),
                "purchaser": result.get("purchaser"),
                "budget": result.get("budget"),
                "deadline": result.get("deadline"),
                "tech_requirements": result.get("tech_requirements", []),
                "scoring_criteria": result.get("scoring_criteria", []),
                "key_points": result.get("key_points", []),
                "suggested_chapters": result.get("suggested_chapters", []),
                "message": "分析完成。",
            }
        )
    except Exception as exc:
        return Response({"message": f"分析失败：{exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        _cleanup_temp_file(cleanup_path)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_outline(request):
    file_obj = request.FILES.get("file")
    if not file_obj:
        return Response({"message": "请先上传文件。"}, status=status.HTTP_400_BAD_REQUEST)

    bid_title = request.query_params.get("bid_title")

    config = _get_user_ai_config(request.user)
    if isinstance(config, Response):
        return config

    file_path, cleanup_path = _write_temp_upload(file_obj)

    from services.bid_analyzer import BidAnalyzer

    analyzer = BidAnalyzer(config)
    try:
        result = analyzer.analyze(file_path)

        title = bid_title or result.get("project_name") or "未命名项目"

        chapters = []
        for index, chapter_title in enumerate(result.get("suggested_chapters", [])):
            chapters.append(
                {
                    "order": index + 1,
                    "title": chapter_title,
                    "estimated_words": 2000,
                }
            )

        if not chapters:
            chapters = [
                {"order": 1, "title": "项目概述", "estimated_words": 1500},
                {"order": 2, "title": "技术方案", "estimated_words": 4000},
                {"order": 3, "title": "实施计划", "estimated_words": 3000},
                {"order": 4, "title": "商务响应", "estimated_words": 1500},
                {"order": 5, "title": "资质与证明材料", "estimated_words": 1000},
            ]

        return Response(
            {
                "success": True,
                "bid_title": title,
                "chapters": chapters,
                "analysis": {
                    "success": True,
                    "project_name": result.get("project_name"),
                    "project_number": result.get("project_number"),
                    "purchaser": result.get("purchaser"),
                    "budget": result.get("budget"),
                    "deadline": result.get("deadline"),
                    "tech_requirements": result.get("tech_requirements", []),
                    "scoring_criteria": result.get("scoring_criteria", []),
                    "key_points": result.get("key_points", []),
                    "suggested_chapters": result.get("suggested_chapters", []),
                },
                "message": "大纲生成成功。",
            }
        )
    except Exception as exc:
        return Response({"message": f"大纲生成失败：{exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        _cleanup_temp_file(cleanup_path)


def _get_user_ai_config(user):
    try:
        return AIConfig.objects.get(user=user, is_active=True)
    except AIConfig.DoesNotExist:
        return Response({"message": "请先配置一个启用中的 AI 设置。"}, status=status.HTTP_400_BAD_REQUEST)


def _get_user_bid_or_404(request, bid_id):
    return get_object_or_404(Bid.objects.filter(user=request.user), id=bid_id)


def _write_temp_upload(file_obj):
    validate_uploaded_file(file_obj)
    suffix = Path(file_obj.name or "").suffix or ".tmp"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        for chunk in file_obj.chunks():
            tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name, tmp.name


def _cleanup_temp_file(path):
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass
