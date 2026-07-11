from django.db.models import Q
from rest_framework import serializers

from apps.agents.models import (
    Agent,
    AgentArtifact,
    AgentMemory,
    AgentRun,
    AgentStep,
    MultiAgentWorkflow,
    WorkflowArtifact,
    WorkflowNodeRun,
)
from apps.files.models import UploadedFile
from apps.files.serializers import UploadedFileSerializer
from apps.tools import schemas


def _dedupe_strings(values):
    items = []
    seen = set()
    for value in values or []:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _dedupe_integers(values):
    items = []
    seen = set()
    for value in values or []:
        try:
            current = int(value)
        except (TypeError, ValueError):
            continue
        if current <= 0 or current in seen:
            continue
        seen.add(current)
        items.append(current)
    return items


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = [
            "id",
            "name",
            "slug",
            "skill",
            "system_prompt",
            "default_max_steps",
            "allowed_tools",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentUpsertSerializer(serializers.ModelSerializer):
    allowed_tools = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = Agent
        fields = [
            "name",
            "slug",
            "skill",
            "system_prompt",
            "default_max_steps",
            "allowed_tools",
            "is_active",
        ]
        extra_kwargs = {
            "skill": {"allow_blank": True, "required": False},
            "system_prompt": {"allow_blank": True, "required": False},
        }

    def validate_allowed_tools(self, value):
        normalized = _dedupe_strings(value)
        known = set(schemas.available_tool_names())
        invalid = [name for name in normalized if name not in known]
        if invalid:
            raise serializers.ValidationError(f"Unknown tools: {', '.join(invalid)}")
        return normalized


class CreateAgentRunSerializer(serializers.Serializer):
    task = serializers.CharField()
    agent_id = serializers.IntegerField(required=False, allow_null=True)
    max_steps = serializers.IntegerField(required=False, min_value=1, max_value=24)
    memory_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )
    file_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )

    def validate_memory_ids(self, value):
        return _dedupe_integers(value)

    def validate_file_ids(self, value):
        return _dedupe_integers(value)


class AgentStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentStep
        fields = [
            "id",
            "order",
            "type",
            "status",
            "thought",
            "tool_name",
            "tool_args",
            "tool_result",
            "content",
            "created_at",
        ]
        read_only_fields = fields


class AgentMemorySerializer(serializers.ModelSerializer):
    run_id = serializers.IntegerField(source="run.id", read_only=True, allow_null=True)

    class Meta:
        model = AgentMemory
        fields = [
            "id",
            "run_id",
            "title",
            "content",
            "scope",
            "tags",
            "pinned",
            "metadata",
            "last_used_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentMemoryUpsertSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=128)
    content = serializers.CharField()
    scope = serializers.ChoiceField(choices=AgentMemory.SCOPE_CHOICES, default="workspace")
    tags = serializers.ListField(
        child=serializers.CharField(max_length=48),
        required=False,
        allow_empty=True,
    )
    pinned = serializers.BooleanField(required=False, default=False)
    metadata = serializers.JSONField(required=False)
    run_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate_tags(self, value):
        return _dedupe_strings(value)[:24]

    def _resolve_run(self, run_id):
        if run_id is None:
            return None

        user = self.context["user"]
        try:
            return AgentRun.objects.get(id=run_id, user=user)
        except AgentRun.DoesNotExist as exc:
            raise serializers.ValidationError({"run_id": "Run not found for this user."}) from exc

    def create(self, validated_data):
        run = self._resolve_run(validated_data.pop("run_id", None))
        return AgentMemory.objects.create(
            user=self.context["user"],
            run=run,
            metadata=validated_data.pop("metadata", {}) or {},
            tags=validated_data.pop("tags", []) or [],
            **validated_data,
        )

    def update(self, instance, validated_data):
        if "run_id" in validated_data:
            instance.run = self._resolve_run(validated_data.pop("run_id"))
        if "metadata" in validated_data:
            instance.metadata = validated_data.pop("metadata") or {}
        if "tags" in validated_data:
            instance.tags = validated_data.pop("tags") or []
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class SaveRunMemorySerializer(serializers.Serializer):
    title = serializers.CharField(max_length=128, required=False, allow_blank=True)
    content = serializers.CharField(required=False, allow_blank=True)
    scope = serializers.ChoiceField(choices=AgentMemory.SCOPE_CHOICES, default="workspace")
    tags = serializers.ListField(
        child=serializers.CharField(max_length=48),
        required=False,
        allow_empty=True,
    )
    pinned = serializers.BooleanField(required=False, default=False)

    def validate_tags(self, value):
        return _dedupe_strings(value)[:24]


class AgentArtifactSerializer(serializers.ModelSerializer):
    run_id = serializers.IntegerField(source="run.id", read_only=True)
    step_id = serializers.IntegerField(source="step.id", read_only=True, allow_null=True)

    class Meta:
        model = AgentArtifact
        fields = [
            "id",
            "run_id",
            "step_id",
            "key",
            "title",
            "artifact_type",
            "source",
            "payload",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AgentRunArtifactSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    run_id = serializers.IntegerField(required=False, allow_null=True)
    step_id = serializers.IntegerField(required=False, allow_null=True)
    key = serializers.CharField()
    title = serializers.CharField()
    artifact_type = serializers.CharField()
    source = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.JSONField()
    metadata = serializers.JSONField(required=False)
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(required=False, allow_null=True)


class AgentRunListSerializer(serializers.ModelSerializer):
    agent = AgentSerializer(read_only=True)
    answer_preview = serializers.SerializerMethodField()

    class Meta:
        model = AgentRun
        fields = [
            "id",
            "agent",
            "task",
            "status",
            "answer_preview",
            "error",
            "step_count",
            "max_steps",
            "tools_used",
            "memory_ids",
            "file_ids",
            "session_id",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_answer_preview(self, obj):
        answer = obj.answer or ""
        return answer[:180] if answer else ""


class AgentRunDetailSerializer(AgentRunListSerializer):
    answer = serializers.CharField(read_only=True)
    steps = AgentStepSerializer(many=True, read_only=True)
    artifacts = AgentArtifactSerializer(many=True, read_only=True)
    memories = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()

    class Meta(AgentRunListSerializer.Meta):
        fields = AgentRunListSerializer.Meta.fields + ["answer", "steps", "artifacts", "memories", "files"]

    def get_memories(self, obj):
        memory_ids = _dedupe_integers(obj.memory_ids)
        query = Q(run_id=obj.id)
        if memory_ids:
            query |= Q(id__in=memory_ids)
        queryset = AgentMemory.objects.filter(user=obj.user).filter(query).order_by(
            "-pinned",
            "-last_used_at",
            "-updated_at",
            "-id",
        )
        return AgentMemorySerializer(queryset, many=True).data

    def get_files(self, obj):
        file_ids = _dedupe_integers(obj.file_ids)
        if not file_ids:
            return []

        queryset = UploadedFile.objects.filter(user=obj.user, id__in=file_ids)
        files_by_id = {uploaded.id: uploaded for uploaded in queryset}
        ordered = [files_by_id[file_id] for file_id in file_ids if file_id in files_by_id]
        return UploadedFileSerializer(ordered, many=True, context=self.context).data


class CreateMultiAgentWorkflowSerializer(serializers.Serializer):
    objective = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    include_child_chapters = serializers.BooleanField(required=False, default=False)


class WorkflowArtifactSerializer(serializers.ModelSerializer):
    node_id = serializers.IntegerField(source="node.id", read_only=True)

    class Meta:
        model = WorkflowArtifact
        fields = ["id", "node_id", "key", "title", "artifact_type", "payload", "created_at", "updated_at"]


class WorkflowNodeRunSerializer(serializers.ModelSerializer):
    agent_slug = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowNodeRun
        fields = [
            "id",
            "agent_id",
            "agent_slug",
            "agent_run_id",
            "chapter_id",
            "key",
            "label",
            "node_type",
            "status",
            "order",
            "depends_on",
            "input_artifacts",
            "output_artifacts",
            "summary",
            "error",
            "metadata",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]

    def get_agent_slug(self, obj):
        return obj.agent.slug if obj.agent_id and obj.agent else None


class MultiAgentWorkflowListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultiAgentWorkflow
        fields = [
            "id",
            "bid_id",
            "kind",
            "title",
            "objective",
            "status",
            "current_node_key",
            "node_count",
            "completed_nodes",
            "error",
            "metadata",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
        ]


class MultiAgentWorkflowDetailSerializer(MultiAgentWorkflowListSerializer):
    nodes = WorkflowNodeRunSerializer(many=True, read_only=True)
    artifacts = WorkflowArtifactSerializer(many=True, read_only=True)

    class Meta(MultiAgentWorkflowListSerializer.Meta):
        fields = MultiAgentWorkflowListSerializer.Meta.fields + ["nodes", "artifacts"]
