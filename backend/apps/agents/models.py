from django.conf import settings
from django.db import models
from django.utils import timezone


class Agent(models.Model):
    """Reusable agent definition bound to a local skill path."""

    name = models.CharField(max_length=128, verbose_name="Name")
    slug = models.CharField(max_length=64, unique=True, verbose_name="Slug")
    skill = models.CharField(
        max_length=128,
        default="bid-writing/bid-chapter-writer",
        help_text="Skill path under hermes_skills without the .md suffix.",
        verbose_name="Skill",
    )
    system_prompt = models.TextField(
        blank=True,
        default="",
        help_text="Extra system prompt content appended after the skill body.",
    )
    default_max_steps = models.IntegerField(default=8, verbose_name="Default max steps")
    allowed_tools = models.JSONField(
        default=list,
        blank=True,
        help_text="Whitelisted tool names. Leave empty to allow all registered tools.",
        verbose_name="Allowed tools",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agents"
        ordering = ["name"]
        verbose_name = "Agent"
        verbose_name_plural = "Agents"

    def __str__(self):
        return self.name


class AgentRun(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_runs",
        verbose_name="User",
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
        verbose_name="Agent",
    )
    task = models.TextField(verbose_name="Task")
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    answer = models.TextField(blank=True, default="", verbose_name="Final answer")
    error = models.TextField(blank=True, default="", verbose_name="Error")
    step_count = models.IntegerField(default=0, verbose_name="Step count")
    max_steps = models.IntegerField(default=8, verbose_name="Max steps")
    tools_used = models.JSONField(default=list, blank=True, verbose_name="Tools used")
    memory_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Selected memory record IDs attached to this run.",
        verbose_name="Memory ids",
    )
    file_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Selected uploaded file IDs attached to this run.",
        verbose_name="File ids",
    )
    session_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Hermes session key used across the run.",
        verbose_name="Session ID",
    )
    celery_task_id = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_runs"
        ordering = ["-created_at"]
        verbose_name = "Agent run"
        verbose_name_plural = "Agent runs"

    def __str__(self):
        return f"Run#{self.id} [{self.status}] {self.task[:40]}"

    def update_status_atomic(self, status, **fields):
        from django.db import transaction

        update_fields = {"status": status, "updated_at": timezone.now()}
        update_fields.update(fields)
        with transaction.atomic():
            return AgentRun.objects.filter(
                id=self.id,
                status__in=["pending", "running"],
            ).update(**update_fields)


class AgentStep(models.Model):
    TYPE_CHOICES = [
        ("plan", "Plan"),
        ("tool_call", "Tool call"),
        ("tool_result", "Tool result"),
        ("answer", "Answer"),
        ("error", "Error"),
    ]
    STATUS_CHOICES = [
        ("ok", "OK"),
        ("error", "Error"),
        ("skipped", "Skipped"),
    ]

    run = models.ForeignKey(
        AgentRun,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name="Run",
    )
    order = models.IntegerField(default=0, verbose_name="Order")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES, verbose_name="Type")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="ok")
    thought = models.TextField(blank=True, default="", verbose_name="Thought")
    tool_name = models.CharField(max_length=64, blank=True, default="", verbose_name="Tool name")
    tool_args = models.JSONField(default=dict, blank=True, verbose_name="Tool args")
    tool_result = models.JSONField(null=True, blank=True, verbose_name="Tool result")
    content = models.JSONField(null=True, blank=True, verbose_name="Content")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "agent_steps"
        ordering = ["order", "id"]
        verbose_name = "Agent step"
        verbose_name_plural = "Agent steps"

    def __str__(self):
        return f"Step#{self.id} run={self.run_id} {self.type} {self.status}"


class AgentArtifact(models.Model):
    """Persisted outputs produced during a run."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_artifacts",
    )
    run = models.ForeignKey(
        AgentRun,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    step = models.ForeignKey(
        AgentStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="artifacts",
    )
    key = models.CharField(max_length=128)
    title = models.CharField(max_length=128, default="")
    artifact_type = models.CharField(max_length=32, default="json")
    source = models.CharField(max_length=32, default="system")
    payload = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_artifacts"
        ordering = ["created_at", "id"]
        unique_together = ("run", "key")

    def __str__(self):
        return f"Artifact#{self.id} run={self.run_id} {self.key}"


class AgentMemory(models.Model):
    """User-scoped memory records that can be attached to runs."""

    SCOPE_CHOICES = [
        ("user", "User"),
        ("workspace", "Workspace"),
        ("run", "Run"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_memories",
    )
    run = models.ForeignKey(
        AgentRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_records",
    )
    title = models.CharField(max_length=128)
    content = models.TextField()
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default="workspace", db_index=True)
    tags = models.JSONField(default=list, blank=True)
    pinned = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_memories"
        ordering = ["-pinned", "-last_used_at", "-updated_at", "-id"]

    def __str__(self):
        return f"Memory#{self.id} {self.scope} {self.title}"


class MultiAgentWorkflow(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    KIND_CHOICES = [
        ("bid_pipeline", "Bid pipeline"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="multi_agent_workflows",
    )
    bid = models.ForeignKey(
        "bids.Bid",
        on_delete=models.CASCADE,
        related_name="multi_agent_workflows",
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default="bid_pipeline", db_index=True)
    title = models.CharField(max_length=256, default="")
    objective = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    current_node_key = models.CharField(max_length=64, blank=True, default="")
    error = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    node_count = models.IntegerField(default=0)
    completed_nodes = models.IntegerField(default=0)
    celery_task_id = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "multi_agent_workflows"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Workflow#{self.id} [{self.status}] {self.title or self.bid_id}"

    def update_status_atomic(self, status, **fields):
        from django.db import transaction

        update_fields = {"status": status, "updated_at": timezone.now()}
        update_fields.update(fields)
        with transaction.atomic():
            return MultiAgentWorkflow.objects.filter(
                id=self.id,
                status__in=["pending", "running"],
            ).update(**update_fields)


class WorkflowNodeRun(models.Model):
    STATUS_CHOICES = MultiAgentWorkflow.STATUS_CHOICES
    NODE_TYPE_CHOICES = [
        ("analysis", "Analysis"),
        ("planning", "Planning"),
        ("writing", "Writing"),
        ("review", "Review"),
    ]

    workflow = models.ForeignKey(
        MultiAgentWorkflow,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    agent = models.ForeignKey(
        Agent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_nodes",
    )
    chapter = models.ForeignKey(
        "bids.BidChapter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_nodes",
    )
    agent_run = models.ForeignKey(
        AgentRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_nodes",
    )
    key = models.CharField(max_length=64)
    label = models.CharField(max_length=128)
    node_type = models.CharField(max_length=16, choices=NODE_TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    order = models.IntegerField(default=0)
    depends_on = models.JSONField(default=list, blank=True)
    input_artifacts = models.JSONField(default=list, blank=True)
    output_artifacts = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflow_node_runs"
        ordering = ["order", "id"]
        unique_together = ("workflow", "key")

    def __str__(self):
        return f"Node#{self.id} {self.key} [{self.status}]"


class WorkflowArtifact(models.Model):
    workflow = models.ForeignKey(
        MultiAgentWorkflow,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    node = models.ForeignKey(
        WorkflowNodeRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="artifacts",
    )
    key = models.CharField(max_length=64)
    title = models.CharField(max_length=128, default="")
    artifact_type = models.CharField(max_length=32, default="json")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workflow_artifacts"
        ordering = ["created_at", "id"]
        unique_together = ("workflow", "key")

    def __str__(self):
        return f"Artifact#{self.id} {self.key}"
