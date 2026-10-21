import uuid

from django.db import models


class InstanceSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=100, default="SpecHelper")
    primary_color = models.CharField(max_length=7, default="#2563eb")
    short_label = models.CharField(max_length=80, blank=True)
    allow_confrontation = models.BooleanField(default=True)
    language = models.CharField(
        max_length=2, choices=[("en", "English"), ("fr", "French")], default="fr"
    )


class GitHubConnection(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    secret = models.TextField(blank=True)
    account = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="DISCONNECTED")


class AIConnection(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    agent = models.CharField(max_length=20, default="codex", unique=True)
    status = models.CharField(max_length=20, default="UNKNOWN")
    account = models.CharField(max_length=200, blank=True)
    checked_at = models.DateTimeField(null=True)
    enabled = models.BooleanField(default=True)
    availability = models.CharField(max_length=24, default="UNKNOWN")
    retry_after = models.DateTimeField(null=True)


class DatabaseConnection(models.Model):
    name = models.CharField(max_length=100, unique=True)
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=5432)
    database = models.CharField(max_length=100)
    username = models.CharField(max_length=100)
    secret = models.TextField()
    sslmode = models.CharField(max_length=20, default="require")
    status = models.CharField(max_length=20, default="UNKNOWN")


class Environment(models.Model):
    name = models.CharField(max_length=100, unique=True)
    database = models.ForeignKey(
        DatabaseConnection, null=True, blank=True, on_delete=models.PROTECT
    )
    status = models.CharField(max_length=20, default="PENDING")
    error = models.TextField(blank=True)
    synced_at = models.DateTimeField(null=True)
    revision = models.PositiveIntegerField(default=1)
    retired_worktrees = models.JSONField(default=list)


class EnvironmentRepository(models.Model):
    environment = models.ForeignKey(
        Environment, related_name="repositories", on_delete=models.CASCADE
    )
    repository = models.CharField(max_length=255)
    branch = models.CharField(max_length=255)
    sha = models.CharField(max_length=40, blank=True)
    workspace = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["environment", "repository"], name="unique_env_repo")
        ]


class Request(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        QUEUED = "QUEUED"
        UNDERSTANDING = "UNDERSTANDING"
        NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
        ANALYZING = "ANALYZING"
        REVIEWING = "REVIEWING"
        GENERATING_RESULT = "GENERATING_RESULT"
        CONTINUING_CONVERSATION = "CONTINUING_CONVERSATION"
        GENERATING_TICKET = "GENERATING_TICKET"
        READY = "READY"
        PARTIAL = "PARTIAL"
        ERROR = "ERROR"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(Environment, null=True, on_delete=models.SET_NULL)
    environment_name_snapshot = models.CharField(max_length=100, blank=True)
    need = models.TextField()
    status = models.CharField(max_length=30, choices=Status, default=Status.DRAFT, db_index=True)
    baseline = models.JSONField(default=list)
    database_snapshot = models.JSONField(default=dict)
    conversation = models.JSONField(default=list)
    questions = models.JSONField(default=list)
    understanding = models.TextField(blank=True)
    progress = models.JSONField(default=list)
    error = models.TextField(blank=True)
    confrontation = models.BooleanField(default=False)
    language = models.CharField(
        max_length=2, choices=[("en", "English"), ("fr", "French")], default="en"
    )
    primary_session = models.ForeignKey(
        "AISession", null=True, blank=True, related_name="+", on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def session(self):
        return (
            self.primary_session or self.ai_sessions.filter(role="primary").order_by("id").first()
        )


class RequestAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, related_name="attachments", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    path = models.TextField()
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()


class AISession(models.Model):
    request = models.ForeignKey(Request, related_name="ai_sessions", on_delete=models.CASCADE)
    runtime_id = models.CharField(max_length=100, blank=True)
    agent = models.CharField(max_length=20, default="codex")
    usage = models.JSONField(default=dict)
    role = models.CharField(max_length=20, default="primary")
    connection = models.ForeignKey(AIConnection, null=True, on_delete=models.SET_NULL)
    context_id = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "role", "agent"], name="unique_request_role_provider"
            )
        ]


class AnalysisResult(models.Model):
    request = models.OneToOneField(Request, related_name="result", on_delete=models.CASCADE)
    ticket = models.JSONField(default=dict)
    markdown = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Job(models.Model):
    kind = models.CharField(max_length=20)
    target = models.CharField(max_length=100)
    status = models.CharField(max_length=20, default="QUEUED", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)
    payload = models.JSONField(default=dict)


class SkillDefinition(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    instructions = models.TextField()
    enabled = models.BooleanField(default=True)


class AgentProfile(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    mission = models.TextField()
    instructions = models.TextField()
    enabled = models.BooleanField(default=True)
    skills = models.ManyToManyField(SkillDefinition, related_name="agents")


class AnalysisRun(models.Model):
    request = models.ForeignKey(Request, related_name="analysis_runs", on_delete=models.CASCADE)
    job = models.OneToOneField(
        Job, related_name="analysis_run", null=True, on_delete=models.SET_NULL
    )
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=30, default="QUEUED")
    pipeline = models.JSONField(default=list)
    steps = models.JSONField(default=list)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "number"], name="unique_request_run")
        ]


class ResultVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, related_name="versions", on_delete=models.CASCADE)
    run = models.ForeignKey(AnalysisRun, null=True, on_delete=models.SET_NULL)
    number = models.PositiveIntegerField()
    format_version = models.CharField(max_length=5, default="1.2")
    language = models.CharField(
        max_length=2, choices=[("en", "English"), ("fr", "French")], default="en"
    )
    status = models.CharField(max_length=30, default="READY")
    ticket = models.JSONField(default=dict)
    technical_summary = models.TextField(blank=True)
    baseline = models.JSONField(default=list)
    database_snapshot = models.JSONField(default=dict)
    environment_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["request", "number"], name="unique_result_version")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A published result version is immutable")
        return super().save(*args, **kwargs)


class GeneratedArtifact(models.Model):
    version = models.ForeignKey(ResultVersion, related_name="artifacts", on_delete=models.CASCADE)
    name = models.CharField(
        max_length=20, choices=[("ticket.md", "ticket.md"), ("goal.md", "goal.md")]
    )
    content = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "name"], name="unique_version_artifact")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A published artifact is immutable")
        return super().save(*args, **kwargs)


class RequestMessage(models.Model):
    request = models.ForeignKey(Request, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=[("user", "User"), ("assistant", "Assistant")])
    kind = models.CharField(max_length=30)
    content = models.TextField()
    data = models.JSONField(default=dict)
    version = models.ForeignKey(ResultVersion, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class ConnectionAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=20)
    status = models.CharField(max_length=20, default="STARTING")
    verification_uri = models.TextField(blank=True)
    user_code = models.CharField(max_length=30, blank=True)
    input_required = models.BooleanField(default=False)
    message = models.TextField(default="Preparing connection…")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
