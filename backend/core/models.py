import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


def default_ai_roles():
    return ["analyst", "counter_analyst", "verifier"]


class InstanceSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=100, default="SpecHelper")
    primary_color = models.CharField(max_length=7, default="#2563eb")
    short_label = models.CharField(max_length=80, blank=True)
    allow_confrontation = models.BooleanField(default=True)
    language = models.CharField(
        max_length=2, choices=[("en", "English"), ("fr", "French")], default="fr"
    )
    orchestration = models.JSONField(default=dict)


class GitHubConnection(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    secret = models.TextField(blank=True)
    account = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="DISCONNECTED")


class GitConnection(models.Model):
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=10, choices=[("github", "GitHub"), ("gitlab", "GitLab")])
    base_url = models.URLField(max_length=1000)
    secret = models.TextField(blank=True)
    account = models.CharField(max_length=200, blank=True)
    enabled = models.BooleanField(default=True)
    legacy_source = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="UNKNOWN")
    error = models.TextField(blank=True)
    checked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_source"],
                condition=models.Q(legacy_source=True),
                name="unique_legacy_git_source",
            )
        ]


class GitRepository(models.Model):
    connection = models.ForeignKey(
        GitConnection, related_name="repositories", on_delete=models.PROTECT
    )
    provider = models.CharField(max_length=10)
    instance = models.URLField(max_length=1000)
    remote_id = models.CharField(max_length=255)
    path = models.CharField(max_length=500)
    name = models.CharField(max_length=255)
    clone_url = models.URLField(max_length=1500)
    default_branch = models.CharField(max_length=255, blank=True)
    is_fork = models.BooleanField(default=False)
    parent = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "remote_id"], name="unique_connection_remote"
            )
        ]


class AIIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.CharField(max_length=20)
    credential_id = models.UUIDField(null=True, unique=True)
    account = models.CharField(max_length=200, blank=True)
    account_key = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, default="UNKNOWN")
    availability = models.CharField(max_length=24, default="UNKNOWN")
    retry_after = models.DateTimeField(null=True)
    checked_at = models.DateTimeField(null=True)
    quota_windows = models.JSONField(default=dict)


class AIConnection(models.Model):
    id = models.AutoField(primary_key=True)
    agent = models.CharField(max_length=20, default="codex")
    name = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    preference = models.PositiveIntegerField(default=100)
    is_default = models.BooleanField(default=False)
    roles = models.JSONField(default=default_ai_roles)
    additional_instructions = models.TextField(blank=True)
    skill_overrides = models.JSONField(default=dict)
    identity = models.ForeignKey(
        AIIdentity, null=True, on_delete=models.PROTECT, related_name="configurations"
    )
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
    context_instructions = models.TextField(blank=True)
    instructions_enabled = models.BooleanField(default=True)
    context_revision = models.PositiveIntegerField(default=1)
    official_references = models.JSONField(default=list)
    library_selection = models.JSONField(default=dict)
    library_revision = models.PositiveIntegerField(default=1)


class ContextResource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(
        Environment, null=True, on_delete=models.SET_NULL, related_name="context_resources"
    )
    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    removed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ContextResourceVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(ContextResource, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    path = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["resource", "version"], name="unique_context_version")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A context resource version is immutable")
        return super().save(*args, **kwargs)


class EnvironmentRepository(models.Model):
    environment = models.ForeignKey(
        Environment, related_name="repositories", on_delete=models.CASCADE
    )
    repository = models.CharField(max_length=255)
    git_repository = models.ForeignKey(
        GitRepository,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="environment_repositories",
    )
    branch = models.CharField(max_length=255)
    sha = models.CharField(max_length=40, blank=True)
    workspace = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["environment", "repository"], name="unique_env_repo")
        ]


class Request(models.Model):
    class Workflow(models.TextChoices):
        REQUEST = "request", "Request"
        QUESTION = "question", "Question"

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
        CANCELLED = "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    environment = models.ForeignKey(Environment, null=True, on_delete=models.SET_NULL)
    environment_name_snapshot = models.CharField(max_length=100, blank=True)
    need = models.TextField()
    scope_assessment = models.JSONField(default=dict)
    scope_history = models.JSONField(default=list)
    scope_clarification = models.TextField(blank=True)
    scope_pending_message = models.TextField(blank=True)
    scope_revision = models.PositiveIntegerField(default=0)
    workflow = models.CharField(max_length=10, choices=Workflow, default=Workflow.REQUEST)
    intent_mode = models.CharField(
        max_length=10, choices=[("explicit", "Explicit"), ("auto", "Automatic")], default="explicit"
    )
    category = models.CharField(max_length=20, default="auto")
    analysis_protocol = models.CharField(max_length=10, default="legacy")
    source_question_version = models.ForeignKey(
        "ResultVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="derived_requests",
    )
    status = models.CharField(max_length=30, choices=Status, default=Status.DRAFT, db_index=True)
    context_snapshot = models.JSONField(default=dict)
    baseline = models.JSONField(default=list)
    database_snapshot = models.JSONField(default=dict)
    conversation = models.JSONField(default=list)
    questions = models.JSONField(default=list)
    understanding = models.TextField(blank=True)
    decision_revision = models.PositiveIntegerField(default=0)
    validated_version = models.PositiveIntegerField(null=True, blank=True)
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
    source_question_version = models.ForeignKey(
        "ResultVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transferred_attachments",
    )


class AISession(models.Model):
    request = models.ForeignKey(Request, related_name="ai_sessions", on_delete=models.CASCADE)
    runtime_id = models.CharField(max_length=100, blank=True)
    agent = models.CharField(max_length=20, default="codex")
    usage = models.JSONField(default=dict)
    role = models.CharField(max_length=20, default="primary")
    connection = models.ForeignKey(AIConnection, null=True, on_delete=models.SET_NULL)
    context_id = models.UUIDField(default=uuid.uuid4, unique=True)
    model_snapshot = models.CharField(max_length=100, blank=True)
    connection_name_snapshot = models.CharField(max_length=100, blank=True)
    identity_snapshot = models.UUIDField(null=True)
    public_role = models.CharField(max_length=30, blank=True)
    family_snapshot = models.CharField(max_length=100, blank=True)


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


class StepExecution(models.Model):
    """Durable, fenced invocation of one sequential checkpoint in a shared job."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="executions")
    checkpoint = models.CharField(max_length=80)
    public_role = models.CharField(max_length=30)
    status = models.CharField(max_length=20, default="QUEUED", db_index=True)
    attempt_id = models.UUIDField(default=uuid.uuid4, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    connection = models.ForeignKey(AIConnection, null=True, on_delete=models.SET_NULL)
    session = models.ForeignKey("AISession", null=True, on_delete=models.SET_NULL)
    instruction_snapshot = models.JSONField(default=dict)
    skill_snapshot = models.JSONField(default=dict)
    loaded_skills = models.JSONField(default=list)
    output = models.JSONField(default=dict)
    owner = models.CharField(max_length=100, blank=True)
    process_id = models.PositiveIntegerField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "checkpoint"], name="unique_job_checkpoint"),
            models.UniqueConstraint(
                fields=["job"], condition=models.Q(status="RUNNING"), name="one_active_step_per_job"
            ),
        ]


class SkillDefinition(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    instructions = models.TextField()
    enabled = models.BooleanField(default=True)
    objective = models.TextField(blank=True)
    compatibility = models.JSONField(default=list)
    required_capabilities = models.JSONField(default=list)
    expected_checks = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    deleted = models.BooleanField(default=False)


class AgentProfile(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=100)
    mission = models.TextField()
    instructions = models.TextField()
    enabled = models.BooleanField(default=True)
    skills = models.ManyToManyField(SkillDefinition, related_name="agents")
    compatibility = models.JSONField(default=list)
    required_capabilities = models.JSONField(default=list)
    expected_checks = models.JSONField(default=list)
    version = models.PositiveIntegerField(default=1)
    deleted = models.BooleanField(default=False)


class LibraryRevision(models.Model):
    """Immutable declarative definitions; no runtime commands or credentials."""

    kind = models.CharField(max_length=10, choices=[("agent", "Agent"), ("skill", "Skill")])
    slug = models.SlugField()
    version = models.PositiveIntegerField()
    definition = models.JSONField()
    action = models.CharField(max_length=20, default="created")
    editor = models.CharField(max_length=100, default="administrator")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "slug", "version"], name="unique_library_revision"
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A library revision is immutable")
        return super().save(*args, **kwargs)


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
    orchestration = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)
    context_snapshot = models.JSONField(default=dict)
    context_usage = models.JSONField(default=list)

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
    explanation = models.JSONField(default=dict)
    technical_summary = models.TextField(blank=True)
    context_usage = models.JSONField(default=list)
    decisions_snapshot = models.JSONField(default=list)
    business_summary = models.JSONField(default=dict)
    evidence = models.JSONField(default=dict)
    context_snapshot = models.JSONField(default=dict)
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
        max_length=20,
        choices=[("ticket.md", "ticket.md"), ("goal.md", "goal.md"), ("answer.md", "answer.md")],
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


class QuestionDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_version = models.ForeignKey(
        ResultVersion, related_name="documents", on_delete=models.PROTECT
    )
    kind = models.CharField(
        max_length=10,
        choices=[("business", "Business"), ("technical", "Technical"), ("mixed", "Mixed")],
    )
    markdown = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A question document is immutable")
        if self.source_version.request.workflow != Request.Workflow.QUESTION:
            raise ValueError("Documentation requires a question answer")
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
    identity = models.ForeignKey(AIIdentity, null=True, on_delete=models.PROTECT)
    git_connection = models.ForeignKey(GitConnection, null=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="STARTING")
    verification_uri = models.TextField(blank=True)
    user_code = models.CharField(max_length=30, blank=True)
    input_required = models.BooleanField(default=False)
    message = models.TextField(default="Preparing connection…")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()


class TicketConnector(models.Model):
    class Platform(models.TextChoices):
        GITHUB = "github", "GitHub"
        GITLAB = "gitlab", "GitLab"
        JIRA = "jira", "Jira"
        GLPI = "glpi", "GLPI"

    environment = models.ForeignKey(
        Environment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ticket_connectors",
    )
    name = models.CharField(max_length=100)
    platform = models.CharField(max_length=10, choices=Platform)
    base_url = models.URLField(max_length=1000)
    username = models.CharField(max_length=255, blank=True)
    secret = models.TextField(blank=True)
    app_token = models.TextField(blank=True)
    api_version = models.CharField(max_length=20, default="v1")
    projects = models.JSONField(default=list)
    default_project = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default="UNKNOWN")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PublishedTicket(models.Model):
    class Status(models.TextChoices):
        PUBLISHING = "PUBLISHING"
        PUBLISHED = "PUBLISHED"
        ERROR = "ERROR"
        UNCERTAIN = "UNCERTAIN"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(Request, related_name="published_tickets", on_delete=models.PROTECT)
    version = models.ForeignKey(
        ResultVersion, related_name="published_tickets", on_delete=models.PROTECT
    )
    connector = models.ForeignKey(
        TicketConnector, related_name="published_tickets", on_delete=models.PROTECT
    )
    platform = models.CharField(max_length=10)
    project = models.CharField(max_length=255)
    destination = models.CharField(max_length=64)
    idempotency_key = models.UUIDField(unique=True)
    external_reference = models.CharField(max_length=80, unique=True)
    title = models.CharField(max_length=500)
    body = models.TextField()
    fields = models.JSONField(default=dict)
    snapshot = models.JSONField(default=dict)
    attachment_delivery = models.JSONField(default=list)
    payload_hash = models.CharField(max_length=64)
    external_id = models.CharField(max_length=255, blank=True)
    external_key = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=2000, blank=True)
    status = models.CharField(
        max_length=20, choices=Status, default=Status.PUBLISHING, db_index=True
    )
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True)

    @property
    def observed_status(self):
        # A killed HTTP worker cannot finalize its state. Report the uncertainty
        # without inventing success or authorizing another external write.
        if self.status == self.Status.PUBLISHING and self.updated_at < timezone.now() - timedelta(
            seconds=90
        ):
            return self.Status.UNCERTAIN
        return self.status

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "destination"],
                condition=~models.Q(status="ERROR"),
                name="unique_version_ticket_destination",
            ),
            models.UniqueConstraint(
                fields=["platform", "destination", "external_id"],
                condition=~models.Q(external_id=""),
                name="unique_external_ticket_identity",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(
                "A publication snapshot is immutable; only its delivery state may change"
            )
        if self.request_id != self.version.request_id:
            raise ValueError("The published version does not belong to this request")
        return super().save(*args, **kwargs)


class TicketPublicationDraft(models.Model):
    """Mutable presentation of one immutable analysis version for one destination."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(
        ResultVersion, related_name="ticket_drafts", on_delete=models.CASCADE
    )
    connector = models.ForeignKey(
        TicketConnector, related_name="ticket_drafts", on_delete=models.CASCADE
    )
    project = models.CharField(max_length=255)
    presentation = models.JSONField(default=dict)
    content = models.JSONField(default=dict)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "connector", "project"], name="unique_ticket_draft_destination"
            )
        ]


# Register security tables while keeping shared workspace models independent.
from .security_models import AccessSession, SecurityBucket, SecurityEvent  # noqa: E402,F401


class AIModel(models.Model):
    """Provider model identifiers from adapter metadata or explicit administration."""

    agent = models.CharField(max_length=20)
    identifier = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    family = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=20, default="administered")
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["agent", "identifier"], name="unique_provider_model")
        ]


class AIModelObservation(models.Model):
    """Account-scoped availability evidence, distinct from account quota."""

    model = models.ForeignKey(AIModel, on_delete=models.CASCADE, related_name="observations")
    identity = models.ForeignKey(AIIdentity, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default="UNKNOWN")
    reason = models.CharField(max_length=40, blank=True)
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["model", "identity"], name="unique_identity_model_status"
            )
        ]


class AIModelDiscovery(models.Model):
    identity = models.OneToOneField(AIIdentity, on_delete=models.CASCADE)
    state = models.CharField(max_length=20, default="unknown")
    reason = models.CharField(max_length=40, blank=True)
    checked_at = models.DateTimeField(auto_now=True)


class LibraryDraft(models.Model):
    """Human-reviewed declarative proposals, separate from the active library."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=5)
    connection = models.ForeignKey(AIConnection, on_delete=models.PROTECT)
    language = models.CharField(max_length=2, default="en")
    status = models.CharField(max_length=24, default="DRAFT")
    revision = models.PositiveIntegerField(default=1)
    definition = models.JSONField(null=True)
    messages = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    test_result = models.JSONField(null=True)
    activated_definition = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LibraryDraftRevision(models.Model):
    draft = models.ForeignKey(LibraryDraft, on_delete=models.PROTECT, related_name="versions")
    revision = models.PositiveIntegerField()
    definition = models.JSONField(null=True)
    action = models.CharField(max_length=24)
    editor = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["draft", "revision"], name="unique_draft_revision")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A draft revision is immutable")
        return super().save(*args, **kwargs)


class BusinessDecision(models.Model):
    """An immutable human choice; the latest sequence per key is the current rule."""

    request = models.ForeignKey(
        Request, on_delete=models.PROTECT, related_name="business_decisions"
    )
    sequence = models.PositiveIntegerField()
    revision = models.PositiveIntegerField()
    key = models.CharField(max_length=100)
    question = models.JSONField()
    option_id = models.CharField(max_length=100, null=True)
    option = models.JSONField(null=True)
    value = models.TextField()
    previous = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    source_version = models.PositiveIntegerField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["request", "sequence"], name="unique_request_decision_sequence"
            )
        ]
        ordering = ["sequence"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A business decision is immutable")
        return super().save(*args, **kwargs)


class BusinessValidation(models.Model):
    """Human approval and explicit reopening of a published result."""

    request = models.ForeignKey(
        Request, on_delete=models.PROTECT, related_name="business_validations"
    )
    version = models.PositiveIntegerField()
    decision_revision = models.PositiveIntegerField()
    action = models.CharField(
        max_length=10, choices=[("validated", "Validated"), ("reopened", "Reopened")]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A business validation is immutable")
        return super().save(*args, **kwargs)
