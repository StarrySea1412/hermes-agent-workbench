from django.conf import settings
from django.db import models


class Project(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("planning", "Planning"),
        ("writing", "Writing"),
        ("ready", "Ready"),
        ("archived", "Archived"),
    ]

    TYPE_CHOICES = [
        ("presentation", "Presentation"),
        ("report", "Report"),
        ("mixed", "Presentation and report"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=256, db_index=True)
    description = models.TextField(blank=True, default="")
    project_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default="presentation")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft", db_index=True)
    outline = models.JSONField(default=list, blank=True)
    final_content = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    files = models.ManyToManyField("files.UploadedFile", through="ProjectFile", related_name="projects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="project_files")
    file = models.ForeignKey("files.UploadedFile", on_delete=models.CASCADE, related_name="project_links")
    purpose = models.CharField(max_length=64, blank=True, default="reference")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "project_files"
        unique_together = ("project", "file")

    def __str__(self):
        return f"{self.project_id}:{self.file_id}"


class Conversation(models.Model):
    MODE_CHOICES = [
        ("chat", "Chat"),
        ("deck", "Deck"),
        ("report", "Report"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="conversations")
    title = models.CharField(max_length=256, default="Untitled conversation")
    mode = models.CharField(max_length=32, choices=MODE_CHOICES, default="chat")
    summary = models.TextField(blank=True, default="")
    is_pinned = models.BooleanField(default=False)
    # 会话级模型覆盖：非空时 compat 链路用这个模型名（同 provider/base_url），清空回到全局配置
    model_override = models.CharField(max_length=128, blank=True, default="")
    # 聊天回合取消标记（DB 后端，多 worker/多机安全）；回合开始清零，finally 清零
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "conversations"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class Message(models.Model):
    ROLE_CHOICES = [
        ("system", "System"),
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.conversation_id}:{self.role}:{self.id}"
