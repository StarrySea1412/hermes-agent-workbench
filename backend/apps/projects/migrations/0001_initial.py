import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("files", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(db_index=True, max_length=256)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "project_type",
                    models.CharField(
                        choices=[
                            ("presentation", "Presentation"),
                            ("report", "Report"),
                            ("mixed", "Presentation and report"),
                        ],
                        default="presentation",
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("planning", "Planning"),
                            ("writing", "Writing"),
                            ("ready", "Ready"),
                            ("archived", "Archived"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=32,
                    ),
                ),
                ("outline", models.JSONField(blank=True, default=list)),
                ("final_content", models.TextField(blank=True, default="")),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="projects", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"db_table": "projects", "ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="Conversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Untitled conversation", max_length=256)),
                (
                    "mode",
                    models.CharField(choices=[("chat", "Chat"), ("deck", "Deck"), ("report", "Report")], default="deck", max_length=32),
                ),
                ("summary", models.TextField(blank=True, default="")),
                ("is_pinned", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="conversations",
                        to="projects.project",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversations", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"db_table": "conversations", "ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="Message",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("system", "System"), ("user", "User"), ("assistant", "Assistant")], max_length=16)),
                ("content", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="projects.conversation"),
                ),
            ],
            options={"db_table": "conversation_messages", "ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="ProjectFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(blank=True, default="reference", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "file",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_links", to="files.uploadedfile"),
                ),
                (
                    "project",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_files", to="projects.project"),
                ),
            ],
            options={"db_table": "project_files", "unique_together": {("project", "file")}},
        ),
        migrations.AddField(
            model_name="project",
            name="files",
            field=models.ManyToManyField(blank=True, related_name="projects", through="projects.ProjectFile", to="files.uploadedfile"),
        ),
    ]
