from django.urls import path

from apps.agents import views

urlpatterns = [
    path("agent-templates", views.agent_templates),
    path("agent-templates/create", views.create_agent_template),
    path("agent-templates/<int:agent_id>", views.agent_template_detail),
    path("tools", views.agent_tools),
    path("memories", views.agent_memories),
    path("memories/<int:memory_id>", views.agent_memory_detail),
    path("agent-runs", views.agent_runs),
    path("agent-runs/<int:run_id>", views.agent_run_detail),
    path("agent-runs/<int:run_id>/artifacts", views.agent_run_artifacts),
    path("agent-runs/<int:run_id>/memories", views.agent_run_memories),
    path("agent-runs/<int:run_id>/save-memory", views.agent_run_save_memory),
    path("agent-runs/<int:run_id>/cancel", views.cancel_agent_run),
    path("agent-runs/<int:run_id>/execute-stream", views.execute_agent_run_stream),
]
