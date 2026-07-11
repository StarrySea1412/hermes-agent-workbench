import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.agents.skill_loader import get_skill_document, list_skills, skill_exists
from apps.ai_config.models import AIConfig, GenerationTask
from apps.ai_config.serializers import (
    AIConfigCreateSerializer,
    AIModelListRequestSerializer,
    AIConfigSerializer,
    AIConfigUpdateSerializer,
    AIGenerateRequestSerializer,
)
from services.encryption_service import get_encryption
from services.hermes_config_sync import sync_hermes_config_for_user
from services.model_fetch_service import ModelFetchError, fetch_model_list

logger = logging.getLogger("api")


@api_view(["GET", "POST", "PATCH"])
@permission_classes([IsAuthenticated])
def ai_config_view(request):
    if request.method == "GET":
        try:
            config = AIConfig.objects.get(user=request.user)
        except AIConfig.DoesNotExist:
            return Response(None)
        return Response(AIConfigSerializer(config).data)

    if request.method == "POST":
        serializer = AIConfigCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        encrypted_key = get_encryption().encrypt(data["api_key"])
        config, _created = AIConfig.objects.update_or_create(
            user=request.user,
            defaults={
                "provider": data["provider"],
                "api_key_encrypted": encrypted_key,
                "base_url": data["base_url"],
                "model_name": data["model_name"],
                "temperature": data["temperature"],
                "max_tokens": data["max_tokens"],
            },
        )
        _sync_hermes_config(request.user)
        return Response(AIConfigSerializer(config).data, status=status.HTTP_201_CREATED)

    try:
        config = AIConfig.objects.get(user=request.user)
    except AIConfig.DoesNotExist:
        return Response({"message": "AI configuration does not exist."}, status=status.HTTP_404_NOT_FOUND)

    serializer = AIConfigUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if "api_key" in data:
        config.api_key_encrypted = get_encryption().encrypt(data["api_key"])
    for field in ["provider", "base_url", "model_name", "temperature", "max_tokens", "is_active"]:
        if field in data:
            setattr(config, field, data[field])

    config.save()
    _sync_hermes_config(request.user)
    return Response(AIConfigSerializer(config).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def test_ai_config(request):
    try:
        config = AIConfig.objects.get(user=request.user)
    except AIConfig.DoesNotExist:
        return Response({"message": "AI configuration does not exist."}, status=status.HTTP_404_NOT_FOUND)

    from services.ai_service import AIService

    ai_service = AIService(config)
    result = ai_service.test_connection_details()
    if not result.get("success"):
        logger.warning(
            "AI config test failed for user_id=%s provider=%s endpoint=%s model=%s error_type=%s status=%s error=%s",
            request.user.id,
            result.get("provider"),
            result.get("endpoint"),
            result.get("model"),
            result.get("error_type"),
            result.get("status_code"),
            result.get("error"),
        )
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def list_ai_models(request):
    serializer = AIModelListRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    config = AIConfig.objects.filter(user=request.user).first()
    provider = (data.get("provider") or getattr(config, "provider", "") or "openai").strip()
    base_url = (data.get("base_url") or getattr(config, "base_url", "") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if not api_key and config:
        api_key = get_encryption().decrypt(config.api_key_encrypted)

    try:
        result = fetch_model_list(
            base_url=base_url,
            api_key=api_key,
            is_full_url=data.get("is_full_url", False),
            models_url_override=data.get("models_url") or None,
            custom_user_agent=data.get("user_agent") or None,
        )
    except ModelFetchError as exc:
        response_status = status.HTTP_400_BAD_REQUEST if exc.client_error else status.HTTP_502_BAD_GATEWAY
        error_info = {
            "success": False,
            "message": str(exc),
            "provider": provider,
            "base_url": base_url,
            "endpoint": exc.endpoint or "",
            "status_code": exc.status_code,
            "error_type": "ModelFetchError",
            "hint": _model_fetch_hint(exc),
            "error": str(exc),
        }
        logger.warning(
            "Model list fetch failed for user_id=%s provider=%s base_url=%s: %s",
            request.user.id,
            provider,
            base_url,
            exc,
        )
        return Response(error_info, status=response_status)

    models = result["models"]
    return Response(
        {
            "provider": provider,
            "endpoint": result["endpoint"],
            "count": len(models),
            "models": models,
        }
    )


def _model_fetch_hint(exc):
    message = str(exc).lower()
    if exc.status_code == 401:
        return "API Key 无效或缺少模型列表权限。"
    if exc.status_code == 403:
        return "模型列表接口被上游拒绝，常见原因是 Key 权限、IP/Cloudflare 拦截或缺少必要请求头。"
    if exc.status_code in (404, 405):
        return "当前基础 URL 无法推导出可用的 /models 接口，请检查是否需要 /v1 或自定义模型列表地址。"
    if exc.status_code == 429:
        return "上游模型列表接口限流，请稍后重试或更换 Key。"
    if exc.status_code and exc.status_code >= 500:
        return "上游模型列表接口返回服务端错误，请稍后重试或更换 provider。"
    if "cloudflare" in message or "attention required" in message:
        return "请求被 Cloudflare 页面拦截，程序拿到的是 HTML，不是模型 JSON。"
    if "invalid json" in message or "data list" in message:
        return "模型列表接口返回格式不是 OpenAI 兼容的 { data: [...] } JSON。"
    if "failed to fetch" in message:
        return "后端无法连接模型列表接口，请检查网络、TLS 证书、代理或上游地址。"
    return "请检查基础 URL、API Key、模型列表接口兼容性以及上游访问限制。"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_chapter(request):
    serializer = AIGenerateRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    mode = data.get("mode", "fast")
    skill = (data.get("skill") or "").strip()

    from apps.bids.models import BidChapter

    chapter = get_object_or_404(BidChapter.objects.filter(bid__user=request.user), id=data["chapter_id"])

    if mode == "fast":
        if not AIConfig.objects.filter(user=request.user, is_active=True).exists():
            return Response({"message": "Configure AI settings first."}, status=status.HTTP_400_BAD_REQUEST)
    elif mode == "hermes":
        if skill and not skill_exists(skill):
            return Response({"message": f"Hermes skill not found: {skill}"}, status=status.HTTP_400_BAD_REQUEST)

        from services.hermes_service import create_hermes_service

        if not create_hermes_service():
            return Response(
                {
                    "message": "Hermes Agent Gateway is unavailable. Check the runtime before retrying.",
                    "fallback": True,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    running = GenerationTask.objects.filter(
        user=request.user,
        status__in=["pending", "running"],
    ).first()
    if running:
        return Response(
            {
                "message": "Another generation task is already running for this user.",
                "existing_task_id": running.id,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    gen_task = GenerationTask.objects.create(
        user=request.user,
        chapter=chapter,
        mode=mode,
        status="pending",
        prompt=data.get("prompt") or "",
        context=data.get("context") or "",
        skill=skill,
    )

    from apps.ai_config.tasks import generate_chapter_task

    async_result = generate_chapter_task.delay(gen_task.id)
    gen_task.celery_task_id = async_result.id
    gen_task.save(update_fields=["celery_task_id"])

    return Response(
        {
            "task_id": gen_task.id,
            "status": gen_task.status,
            "mode": mode,
            "skill": gen_task.skill or None,
            "message": "Task submitted. Poll the status endpoint for progress.",
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def generation_status(request, task_id):
    try:
        gen_task = GenerationTask.objects.get(id=task_id, user=request.user)
    except GenerationTask.DoesNotExist:
        return Response({"message": "Task not found."}, status=status.HTTP_404_NOT_FOUND)

    response = {
        "task_id": gen_task.id,
        "status": gen_task.status,
        "mode": gen_task.mode,
        "skill": gen_task.skill or None,
    }
    if gen_task.status == "done":
        result = gen_task.result or {}
        response["content"] = result.get("content")
        response["generated_text"] = result.get("generated_text")
    elif gen_task.status == "failed":
        response["error"] = gen_task.error
        response["message"] = f"Generation failed: {gen_task.error}" if gen_task.error else "Generation failed."
    else:
        response["message"] = {
            "pending": "Queued.",
            "running": "Running.",
        }.get(gen_task.status, "")

    return Response(response)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hermes_status(request):
    from services.hermes_service import create_hermes_service

    hermes_service = create_hermes_service()
    if not hermes_service:
        return Response(
            {
                "available": False,
                "connected": False,
                "message": "Hermes Gateway is not configured.",
            }
        )

    status_info = hermes_service.health_check()
    return Response(
        {
            "available": status_info.get("available", False),
            "connected": status_info.get("connected", False),
            "error": status_info.get("error"),
            "message": "Hermes Gateway is online." if status_info.get("connected") else "Hermes Gateway is offline.",
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hermes_skills(request):
    return Response({"skills": list_skills()})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hermes_skill_detail(request, skill_path):
    document = get_skill_document(skill_path)
    if not document:
        return Response({"message": "Hermes skill not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(document)


def _sync_hermes_config(user):
    try:
        result = sync_hermes_config_for_user(user)
        if not result.get("ok"):
            logger.warning("Skipped Hermes config sync for user_id=%s: %s", user.id, result.get("reason"))
    except Exception:
        logger.exception("Hermes config sync failed after AI config update: user_id=%s", user.id)
