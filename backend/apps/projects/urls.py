from django.urls import path

from apps.projects import views

urlpatterns = [
    path("projects/", views.projects, name="projects"),
    path("projects/<int:project_id>/", views.project_detail, name="project-detail"),
    path("projects/<int:project_id>/files/", views.project_files, name="project-files"),
    path("projects/<int:project_id>/export/markdown/", views.export_project_markdown, name="project-export-markdown"),
    path("projects/<int:project_id>/export/docx/", views.export_project_docx, name="project-export-docx"),
    path("conversations/", views.conversations, name="conversations"),
    path("conversations/<int:conversation_id>/", views.conversation_detail, name="conversation-detail"),
    path("conversations/<int:conversation_id>/messages/", views.conversation_messages, name="conversation-messages"),
    path("conversations/<int:conversation_id>/stream/", views.conversation_stream, name="conversation-stream"),
    path("conversations/<int:conversation_id>/cancel/", views.conversation_cancel, name="conversation-cancel"),
]
