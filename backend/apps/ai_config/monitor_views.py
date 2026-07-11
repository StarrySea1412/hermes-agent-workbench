from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def hermes_monitor(request):
    from services.hermes_service import get_hermes_monitor

    include_chat = request.query_params.get("chat", "false").lower() in ("true", "1", "yes")
    status_info = get_hermes_monitor(run_chat_probe=include_chat)
    if status_info.get("connected") and status_info.get("chat_degraded"):
        status_info["message"] = "Hermes Gateway is online; chat probe is slow or unavailable."
    else:
        status_info["message"] = "Hermes Gateway is online." if status_info.get("connected") else "Hermes Gateway is offline."
    return Response(status_info)
