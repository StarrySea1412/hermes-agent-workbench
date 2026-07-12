from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

admin.site.site_header = "Hermes Workbench Admin"
admin.site.site_title = "Hermes Workbench"
admin.site.index_title = "Runtime management"


@api_view(["GET"])
@permission_classes([AllowAny])
def health_view(request):
    return Response({
        "status": "ok",
        "legacy_bids": bool(getattr(settings, "ENABLE_LEGACY_BIDS", False)),
    })


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.agents.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.ai_config.urls")),
    path("api/health", health_view),
    path("api/", include("apps.files.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if getattr(settings, "ENABLE_LEGACY_BIDS", False):
    urlpatterns.insert(4, path("api/", include("apps.bids.urls")))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
