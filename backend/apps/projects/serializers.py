from rest_framework import serializers

from apps.files.models import UploadedFile
from apps.files.serializers import UploadedFileSerializer
from apps.projects.models import Conversation, Message, Project, ProjectFile
from services.hermes_service import build_session_id


class ProjectFileSerializer(serializers.ModelSerializer):
    file = UploadedFileSerializer(read_only=True)
    file_id = serializers.PrimaryKeyRelatedField(
        queryset=UploadedFile.objects.all(),
        source="file",
        write_only=True,
    )

    class Meta:
        model = ProjectFile
        fields = ["id", "file", "file_id", "purpose", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProjectSerializer(serializers.ModelSerializer):
    project_files = ProjectFileSerializer(many=True, read_only=True)
    conversation_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "description",
            "project_type",
            "status",
            "outline",
            "final_content",
            "metadata",
            "project_files",
            "conversation_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "conversation_count"]


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["title", "description", "project_type", "outline", "final_content", "metadata"]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "conversation", "role", "content", "metadata", "created_at"]
        read_only_fields = ["id", "conversation", "role", "metadata", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    project = ProjectSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        source="project",
        required=False,
        allow_null=True,
        write_only=True,
    )
    last_message = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "title",
            "mode",
            "summary",
            "is_pinned",
            "model_override",
            "tool_approval_required",
            "project",
            "project_id",
            "last_message",
            "session_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "summary", "created_at", "updated_at", "last_message", "session_id"]

    def get_last_message(self, obj):
        message = obj.messages.order_by("-created_at").first()
        if not message:
            return None
        return {
            "role": message.role,
            "content": message.content[:140],
            "created_at": message.created_at,
        }

    def get_session_id(self, obj):
        if obj.project_id:
            session_id = build_session_id(obj.user_id, obj.project_id)
            if session_id:
                return session_id
        return f"u{obj.user_id}-c{obj.id}"


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["messages"]


class ChatRequestSerializer(serializers.Serializer):
    content = serializers.CharField()
    project_id = serializers.IntegerField(required=False)
    mode = serializers.ChoiceField(choices=["chat", "deck", "report"], required=False, default="deck")
    stream = serializers.BooleanField(required=False, default=False)
    attachments = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
