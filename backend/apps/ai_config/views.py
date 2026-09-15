import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.agents.skill_loader import get_skill_document, list_skills
from apps.ai_config.cc_switch_service import get_cc_switch_provider, list_cc_switch_providers
from apps.ai_config.models import AIConfig
from apps.ai_config.serializers import (
    AIConfigCreateSerializer,
    AIModelListRequestSerializer,
    AIConfigSerializer,
    AIConfigUpdateSerializer,
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
    for field in ["provider", "base_url", "model_name", "embedding_model_name", "temperature", "max_tokens", "is_active"]:
        if field in data:
            setattr(config, field, data[field])

    config.save()
    _sync_hermes_config(request.user)
    return Response(AIConfigSerializer(config).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cc_switch_providers(request):
    result = list_cc_switch_providers()
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cc_switch_import(request):
    provider_id = str(request.data.get("provider_id") or "").strip()
    if not provider_id:
        return Response({"message": "缺少 provider_id。"}, status=status.HTTP_400_BAD_REQUEST)

    provider = get_cc_switch_provider(provider_id)
    if not provider:
        return Response({"message": "未找到该 CC Switch 供应商，或缺少地址/密钥。"}, status=status.HTTP_404_NOT_FOUND)

    config, _created = AIConfig.objects.update_or_create(
        user=request.user,
        defaults={
            "provider": provider["provider"],
            "api_key_encrypted": get_encryption().encrypt(provider["api_key"]),
            "base_url": provider["base_url"],
            "model_name": provider["model_name"],
        },
    )
    _sync_hermes_config(request.user)
    return Response({
        "message": f"已导入并启用：{provider['name']}（重启 AI-skill 后网关使用新配置）",
        "provider": {
            "name": provider["name"],
            "app_type": provider["app_type"],
            "provider": provider["provider"],
            "base_url": provider["base_url"],
            "model_name": provider["model_name"],
        },
        "config": AIConfigSerializer(config).data,
    })


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
