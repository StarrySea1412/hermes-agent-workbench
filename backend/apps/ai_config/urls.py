from django.urls import path

from apps.ai_config import monitor_views, views

urlpatterns = [
    path('ai-config', views.ai_config_view),
    path('ai-config/cc-switch', views.cc_switch_providers),
    path('ai-config/cc-switch/import', views.cc_switch_import),
    path('ai-config/models', views.list_ai_models),
    path('ai-config/test', views.test_ai_config),
    path('hermes/status', views.hermes_status),
    path('hermes/skills', views.hermes_skills),
    path('hermes/skills/<path:skill_path>', views.hermes_skill_detail),
    path('hermes/monitor', monitor_views.hermes_monitor),
]
