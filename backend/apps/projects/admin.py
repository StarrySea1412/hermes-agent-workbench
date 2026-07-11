from django.contrib import admin

from apps.projects.models import Conversation, Message, Project, ProjectFile


class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "project_type", "status", "user", "updated_at")
    list_filter = ("project_type", "status")
    search_fields = ("title", "description", "user__username")
    inlines = [ProjectFileInline]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "mode", "user", "project", "updated_at")
    list_filter = ("mode", "is_pinned")
    search_fields = ("title", "user__username", "project__title")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("content",)


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "file", "purpose", "created_at")
