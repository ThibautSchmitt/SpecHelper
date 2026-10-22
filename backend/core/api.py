import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import File, NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.responses import Status
from pydantic import Field

from . import connections as connection_flows
from . import environments as environment_actions
from . import github, providers
from .agent import runtime_call
from .models import (
    AgentProfile,
    AIConnection,
    AnalysisResult,
    ConnectionAttempt,
    DatabaseConnection,
    Environment,
    EnvironmentRepository,
    GeneratedArtifact,
    GitHubConnection,
    InstanceSettings,
    Job,
    Request,
    RequestAttachment,
    RequestMessage,
    ResultVersion,
    SkillDefinition,
)
from .postgres import check_connection
from .secrets import encrypt
from .services import add_attachment, continue_conversation, enqueue_analysis

api = NinjaAPI(title="SpecHelper", version="1.8", auth=None)


@api.exception_handler(ValueError)
def invalid(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=422)


class SettingsIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    primary_color: str = Field(pattern=r"^#[a-fA-F0-9]{6}$")
    short_label: str = Field(default="", max_length=80)
    allow_confrontation: bool = True
    language: Literal["en", "fr"] = "fr"


class GitHubIn(Schema):
    token: str = Field(min_length=1, max_length=1000)


class DatabaseIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(default="", max_length=2048)
    host: str = Field(default="", max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="", max_length=100)
    username: str = Field(default="", max_length=100)
    password: str = Field(default="", max_length=1000)
    sslmode: str = Field(default="require", pattern=r"^(require|verify-ca|verify-full|disable)$")


class RepositoryIn(Schema):
    repository: str = Field(default="", max_length=255)
    branch: str = Field(min_length=1, max_length=255)
    git_connection_id: int | None = None
    remote_id: str = Field(default="", max_length=255)
    git_repository_id: int | None = Field(default=None, exclude=True)


class EnvironmentIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    repositories: list[RepositoryIn] = Field(min_length=1)
    database_id: int | None = None


class EnvironmentEditIn(EnvironmentIn):
    expected_revision: int = Field(ge=1)


class EnvironmentDeleteIn(Schema):
    confirm_name: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)


class RequestIn(Schema):
    environment_id: int
    need: str = Field(min_length=10, max_length=30000)
    confrontation: bool = False
    category: Literal["auto", "feature", "bug", "documentation"] = "auto"


class AnswersIn(Schema):
    answers: dict[str, str]


class ContinuationIn(Schema):
    message: str = Field(min_length=1, max_length=30000)
    expected_version: int = Field(ge=1)


class ConnectIn(Schema):
    provider: Literal["github", "codex", "claude"]


class ConnectionOptionsIn(Schema):
    enabled: bool


class AnalysisOptionsIn(Schema):
    agents: dict[str, bool] = Field(default_factory=dict)
    skills: dict[str, bool] = Field(default_factory=dict)


class CodeIn(Schema):
    code: str = Field(min_length=1, max_length=4096)


@api.post("/connections/start")
def start_connection(request, payload: ConnectIn):
    return connection_flows.start(payload.provider)


@api.get("/connections/attempts/{attempt_id}")
def connection_attempt(request, attempt_id: UUID):
    return connection_flows.poll(get_object_or_404(ConnectionAttempt, pk=attempt_id))


@api.post("/connections/attempts/{attempt_id}/code")
def submit_connection_code(request, attempt_id: UUID, payload: CodeIn):
    attempt = get_object_or_404(ConnectionAttempt, pk=attempt_id)
    if attempt.provider != "claude" or attempt.status not in connection_flows.ACTIVE:
        raise HttpError(409, "No confirmation code is expected")
    state = runtime_call("/auth/" + str(attempt.id) + "/code", {"code": payload.code.strip()})
    return connection_flows.update(attempt, state)


@api.post("/connections/attempts/{attempt_id}/cancel")
def cancel_connection(request, attempt_id: UUID):
    return connection_flows.cancel(get_object_or_404(ConnectionAttempt, pk=attempt_id))


def settings_dict():
    value, _ = InstanceSettings.objects.get_or_create(pk=1)
    return {
        "name": value.name,
        "primary_color": value.primary_color,
        "short_label": value.short_label,
        "allow_confrontation": value.allow_confrontation,
        "language": value.language,
    }


def environment_dict(environment):
    from .git_sources import repository_snapshot

    return {
        "id": environment.id,
        "name": environment.name,
        "status": environment.status,
        "revision": environment.revision,
        "error": environment.error,
        "synced_at": environment.synced_at,
        "database_id": environment.database_id,
        "database_name": environment.database.name if environment.database_id else None,
        "repositories": [
            {"id": repo.pk, **repository_snapshot(repo)}
            for repo in environment.repositories.select_related("git_repository__connection")
        ],
    }


def request_dict(value, full=False):
    result = {
        "id": str(value.id),
        "need": value.need,
        "title": value.need.splitlines()[0][:160],
        "workflow": value.workflow,
        "category": value.category,
        "source_question": {
            "id": str(value.source_question_version.request_id),
            "version": value.source_question_version.number,
            "title": value.source_question_version.explanation.get("title", "Question"),
            "href": f"/questions/{value.source_question_version.request_id}?version={value.source_question_version.number}",
        }
        if value.source_question_version_id
        else None,
        "confrontation": value.confrontation,
        "language": value.language,
        "status": value.status,
        "environment_id": value.environment_id,
        "environment_name": value.environment_name_snapshot
        or (value.environment.name if value.environment_id else "Deleted environment"),
        "created_at": value.created_at,
        "updated_at": value.updated_at,
    }
    if full:
        analysis = AnalysisResult.objects.filter(request=value).first()
        result.update(
            {
                "context_snapshot": value.context_snapshot,
                "baseline": value.baseline,
                "database": value.database_snapshot,
                "questions": value.questions,
                "conversation": value.conversation,
                "understanding": value.understanding,
                "progress": value.progress,
                "error": value.error,
                "attachments": [
                    {
                        "id": str(a.id),
                        "name": a.name,
                        "size": a.size,
                        "content_type": a.content_type,
                        "internal": bool(a.source_question_version_id),
                        "source_question": {
                            "id": str(a.source_question_version.request_id),
                            "version": a.source_question_version.number,
                        }
                        if a.source_question_version_id
                        else None,
                    }
                    for a in value.attachments.select_related("source_question_version")
                ],
                "ticket": analysis.ticket if analysis else None,
                "markdown": analysis.markdown if analysis else None,
                "versions": list(
                    value.versions.values("id", "number", "format_version", "status", "created_at")
                ),
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "kind": m.kind,
                        "content": m.content,
                        "created_at": m.created_at,
                        "version_number": m.version.number if m.version_id else None,
                    }
                    for m in value.messages.select_related("version").all()
                ],
                "analysis_runs": list(
                    value.analysis_runs.order_by("number").values(
                        "number",
                        "status",
                        "pipeline",
                        "steps",
                        "started_at",
                        "finished_at",
                        "error",
                        "warnings",
                        "context_snapshot",
                        "context_usage",
                    )
                ),
                "latest_version": version_dict(value.versions.order_by("-number").first()),
            }
        )
    return result


def version_dict(version):
    if version is None:
        return None
    artifacts = {a.name: a.content for a in version.artifacts.all()}
    return {
        "id": str(version.id),
        "number": version.number,
        "format_version": version.format_version,
        "run_number": version.run.number if version.run_id else None,
        "context_snapshot": version.context_snapshot,
        "context_usage": version.context_usage,
        "language": version.language,
        "status": version.status,
        "created_at": version.created_at,
        "ticket": version.ticket,
        "technical_summary": version.technical_summary,
        "baseline": version.baseline,
        "database": version.database_snapshot,
        "environment_name": version.environment_name,
        "markdown": artifacts.get("ticket.md", ""),
        "goal_markdown": artifacts.get("goal.md", ""),
        "artifacts": {
            name: f"/api/requests/{version.request_id}/versions/{version.number}/artifacts/{name}"
            for name in artifacts
        },
    }


@api.get("/health")
def health(request):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return {"status": "ok"}


@api.get("/settings")
def get_settings(request):
    return settings_dict()


@api.put("/settings")
def put_settings(request, payload: SettingsIn):
    InstanceSettings.objects.update_or_create(pk=1, defaults=payload.dict())
    return settings_dict()


@api.get("/connections")
def connections(request):
    from .git_sources import connection_dict
    from .models import GitConnection

    gh, _ = GitHubConnection.objects.get_or_create(pk=1)
    ais = providers.ensure_connections()
    preferred = next(
        (c for c in ais if c.status == "CONNECTED" and c.enabled), next(iter(ais), None)
    )
    return {
        "github": {"status": gh.status, "account": gh.account},
        "ai": providers.public(preferred)
        if preferred
        else {
            "status": "DISCONNECTED",
            "availability": "UNKNOWN",
            "agent": "",
            "enabled": False,
            "account": "",
        },
        "ais": [providers.public(c) for c in ais],
        "git_connections": [
            connection_dict(c) for c in GitConnection.objects.order_by("name", "id")
        ],
        "databases": list(
            DatabaseConnection.objects.values(
                "id", "name", "host", "port", "database", "username", "sslmode", "status"
            )
        ),
    }


@api.put("/connections/github")
def connect_github(request, payload: GitHubIn):
    GitHubConnection.objects.update_or_create(
        pk=1, defaults={"secret": encrypt(payload.token), "status": "UNKNOWN", "account": ""}
    )
    return test_github(request)


@api.post("/connections/github/test")
def test_github(request):
    try:
        account = github.get("/user")["login"]
    except ValueError:
        GitHubConnection.objects.filter(pk=1).update(status="ERROR")
        raise
    GitHubConnection.objects.filter(pk=1).update(status="CONNECTED", account=account)
    return {"status": "CONNECTED", "account": account}


@api.get("/github/organizations")
def organizations(request, page: int = 1):
    return [{"login": o["login"]} for o in github.paginated("/user/orgs", max(1, page))]


@api.get("/github/repositories")
def repositories(request, organization: str = "", page: int = 1):
    if organization and not re.fullmatch(r"[A-Za-z0-9-]+", organization):
        raise HttpError(422, "Invalid organization")
    path = f"/orgs/{organization}/repos" if organization else "/user/repos"
    return [
        {
            "full_name": r["full_name"],
            "private": r["private"],
            "default_branch": r["default_branch"],
        }
        for r in github.paginated(path, max(1, page))
    ]


@api.get("/github/branches")
def branches(request, repository: str, page: int = 1):
    github.validate_repository(repository)
    return [
        {"name": b["name"]} for b in github.paginated(f"/repos/{repository}/branches", max(1, page))
    ]


@api.post("/connections/ai/test")
def test_ai(request):
    connections = providers.ensure_connections()
    if not connections:
        raise HttpError(404, "No AI connection is configured.")
    return test_ai_connection(
        request, next((c.pk for c in connections if c.status == "CONNECTED"), connections[0].pk)
    )


@api.post("/connections/ai/{connection_id}/test")
def test_ai_connection(request, connection_id: int):
    from .ai_api import test_configuration

    return test_configuration(get_object_or_404(AIConnection, pk=connection_id))


@api.patch("/connections/ai/{connection_id}")
def configure_ai(request, connection_id: int, payload: ConnectionOptionsIn):
    from .ai_api import ConfigurationPatch, edit_connection

    return edit_connection(request, connection_id, ConfigurationPatch(enabled=payload.enabled))


def database_values(payload):
    values = payload.model_dump(exclude={"url", "password"})
    password = payload.password
    if payload.url:
        from psycopg.conninfo import conninfo_to_dict

        if not payload.url.startswith(("postgresql://", "postgres://")):
            raise HttpError(422, "Use a valid PostgreSQL URL.")
        try:
            parsed = conninfo_to_dict(payload.url)
            if set(parsed) - {"host", "port", "dbname", "user", "password", "sslmode"}:
                raise ValueError
            values.update(
                {
                    "host": parsed.get("host", ""),
                    "port": int(parsed.get("port", payload.port)),
                    "database": parsed.get("dbname", ""),
                    "username": payload.username or parsed.get("user", ""),
                    "sslmode": parsed.get("sslmode", payload.sslmode),
                }
            )
            password = password or parsed.get("password", "")
        except Exception:
            raise HttpError(422, "Invalid PostgreSQL URL.")
    if not all(values.get(field) for field in ("host", "database", "username")) or not password:
        raise HttpError(422, "Enter the host, database, username and password.")
    if not 1 <= values["port"] <= 65535 or values["sslmode"] not in {
        "require",
        "verify-ca",
        "verify-full",
        "disable",
    }:
        raise HttpError(422, "Invalid PostgreSQL connection options.")
    if len(values["host"]) > 255 or len(values["database"]) > 100 or len(values["username"]) > 100:
        raise HttpError(422, "PostgreSQL parameters are too long.")
    return values, password


@api.post("/connections/databases", response={201: dict})
def create_database(request, payload: DatabaseIn):
    if DatabaseConnection.objects.filter(name=payload.name).exists():
        raise HttpError(409, "This name already exists")
    values, password = database_values(payload)
    connection = DatabaseConnection(**values, secret=encrypt(password))
    check_connection(connection)
    connection.status = "CONNECTED"
    connection.save()
    return Status(
        201,
        {
            "id": connection.id,
            "name": connection.name,
            "status": connection.status,
            "checks": {"connection": True, "read": True, "read_only": True},
        },
    )


@api.post("/connections/databases/{connection_id}/test")
def test_database(request, connection_id: int):
    connection = get_object_or_404(DatabaseConnection, pk=connection_id)
    try:
        check_connection(connection)
    except ValueError:
        connection.status = "ERROR"
        connection.save(update_fields=["status"])
        raise
    connection.status = "CONNECTED"
    connection.save(update_fields=["status"])
    return {
        "status": connection.status,
        "checks": {"connection": True, "read": True, "read_only": True},
    }


@api.get("/environments")
def environments(request):
    return [
        environment_dict(e)
        for e in Environment.objects.select_related("database")
        .prefetch_related("repositories")
        .order_by("name")
    ]


@api.post("/environments", response={201: dict})
@transaction.atomic
def create_environment(request, payload: EnvironmentIn):
    environment_actions.validate(payload)
    environment = Environment.objects.create(name=payload.name, database_id=payload.database_id)
    EnvironmentRepository.objects.bulk_create(
        [
            EnvironmentRepository(
                environment=environment,
                repository=repo.repository,
                branch=repo.branch,
                git_repository_id=repo.git_repository_id,
            )
            for repo in payload.repositories
        ]
    )
    Job.objects.create(kind="sync", target=str(environment.id))
    return Status(201, environment_dict(environment))


@api.post("/environments/{environment_id}/sync")
@transaction.atomic
def sync(request, environment_id: int):
    environment = get_object_or_404(Environment.objects.select_for_update(), pk=environment_id)
    if Job.objects.filter(
        kind="sync", target=str(environment.id), status__in=["QUEUED", "RUNNING"]
    ).exists():
        raise HttpError(409, "Synchronization is already running")
    Job.objects.create(kind="sync", target=str(environment.id))
    environment.status = "PENDING"
    environment.error = ""
    environment.save(update_fields=["status", "error"])
    return {"status": "QUEUED"}


@api.patch("/environments/{environment_id}")
def edit_environment(request, environment_id: int, payload: EnvironmentEditIn):
    return environment_dict(environment_actions.update(environment_id, payload))


@api.delete("/environments/{environment_id}")
def delete_environment(request, environment_id: int, payload: EnvironmentDeleteIn):
    environment_actions.delete(environment_id, payload)
    return {"status": "DELETED"}


@api.get("/requests")
def requests(request):
    return [
        request_dict(r)
        for r in Request.objects.filter(workflow="request")
        .select_related("environment")
        .order_by("-created_at")[:100]
    ]


@api.post("/requests", response={201: dict})
def create_request(request, payload: RequestIn):
    from .creation_policy import automatic_comparison, creation_settings

    options = creation_settings()
    environment = get_object_or_404(Environment, pk=payload.environment_id)
    value = Request.objects.create(
        environment=environment,
        environment_name_snapshot=environment.name,
        need=payload.need,
        confrontation=automatic_comparison(options),
        category=payload.category,
        language=options.language,
    )
    RequestMessage.objects.create(request=value, role="user", kind="need", content=value.need)
    return Status(201, request_dict(value, full=True))


@api.get("/requests/{request_id}")
def get_request(request, request_id: UUID):
    return request_dict(
        get_object_or_404(
            Request.objects.select_related("environment"), pk=request_id, workflow="request"
        ),
        full=True,
    )


@api.post("/requests/{request_id}/attachments", response={201: dict})
def upload_attachment(request, request_id: UUID, file: File[UploadedFile]):
    get_object_or_404(Request, pk=request_id, workflow="request")
    attachment = add_attachment(request_id, file)
    return Status(201, {"id": str(attachment.id), "name": attachment.name, "size": attachment.size})


@api.get("/requests/{request_id}/attachments/{attachment_id}")
def download_attachment(request, request_id: UUID, attachment_id: UUID):
    attachment = get_object_or_404(
        RequestAttachment, pk=attachment_id, request_id=request_id, request__workflow="request"
    )
    response = FileResponse(
        Path(attachment.path).open("rb"),
        as_attachment=True,
        filename=attachment.name,
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api.delete("/requests/{request_id}/attachments/{attachment_id}")
def remove_draft_attachment(request, request_id: UUID, attachment_id: UUID):
    from .question_actions import remove_attachment

    remove_attachment(request_id, attachment_id, "request")
    return {"status": "DELETED"}


@api.post("/requests/{request_id}/analyze")
def start_analysis(request, request_id: UUID):
    get_object_or_404(Request, pk=request_id, workflow="request")
    return request_dict(enqueue_analysis(request_id), full=True)


@api.post("/requests/{request_id}/answers")
def answer_questions(request, request_id: UUID, payload: AnswersIn):
    get_object_or_404(Request, pk=request_id, workflow="request")
    return request_dict(enqueue_analysis(request_id, payload.answers), full=True)


@api.get("/requests/{request_id}/markdown")
def download_markdown(request, request_id: UUID):
    result = get_object_or_404(AnalysisResult, request_id=request_id, request__workflow="request")
    response = HttpResponse(result.markdown, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="spechelper-{request_id}.md"'
    return response


@api.post("/requests/{request_id}/continue")
def continue_request(request, request_id: UUID, payload: ContinuationIn):
    get_object_or_404(Request, pk=request_id, workflow="request")
    return request_dict(
        continue_conversation(request_id, payload.message, payload.expected_version), full=True
    )


@api.get("/requests/{request_id}/versions/{number}")
def get_version(request, request_id: UUID, number: int):
    return version_dict(
        get_object_or_404(
            ResultVersion, request_id=request_id, number=number, request__workflow="request"
        )
    )


@api.get("/requests/{request_id}/versions/{number}/artifacts/{name}")
def download_artifact(
    request, request_id: UUID, number: int, name: Literal["ticket.md", "goal.md"]
):
    artifact = get_object_or_404(
        GeneratedArtifact,
        version__request_id=request_id,
        version__request__workflow="request",
        version__number=number,
        name=name,
    )
    response = HttpResponse(artifact.content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api.get("/agents")
def agents(request):
    from .catalogue import ensure_catalogue

    ensure_catalogue()
    return [
        {
            "slug": profile.slug,
            "name": profile.name,
            "mission": profile.mission,
            "enabled": profile.enabled,
            "instructions": profile.instructions,
            "skills": [
                {"slug": skill.slug, "name": skill.name, "enabled": skill.enabled}
                for skill in profile.skills.all()
            ],
        }
        for profile in AgentProfile.objects.prefetch_related("skills").order_by("slug")
    ]


@api.get("/skills")
def skills(request):
    from .catalogue import ensure_catalogue

    ensure_catalogue()
    return list(
        SkillDefinition.objects.order_by("slug").values("slug", "name", "instructions", "enabled")
    )


@api.get("/analysis-options")
def get_analysis_options(request):
    from .catalogue import ensure_catalogue

    ensure_catalogue()
    return {
        "agents": list(AgentProfile.objects.order_by("slug").values("slug", "name", "enabled")),
        "skills": list(SkillDefinition.objects.order_by("slug").values("slug", "name", "enabled")),
    }


@api.patch("/analysis-options")
@transaction.atomic
def set_analysis_options(request, payload: AnalysisOptionsIn):
    from .catalogue import ensure_catalogue

    ensure_catalogue()
    for model, values in ((AgentProfile, payload.agents), (SkillDefinition, payload.skills)):
        if set(values) - set(model.objects.values_list("slug", flat=True)):
            raise HttpError(422, "Unknown analysis option.")
        for slug, enabled in values.items():
            model.objects.filter(pk=slug).update(enabled=enabled)
    return get_analysis_options(request)


@api.get("/system")
def system(request):
    return {
        "jobs": list(
            Job.objects.order_by("-created_at").values(
                "id", "kind", "target", "status", "started_at", "finished_at", "error"
            )[:30]
        ),
        "usage": "UNKNOWN",
        "runtime": " / ".join(
            "ChatGPT" if c.agent == "codex" else "Claude"
            for c in AIConnection.objects.filter(enabled=True, status="CONNECTED")
        )
        or "No connected assistant",
        "max_analysis_seconds": 300,
    }


@api.get("/queue")
def queue(request):
    from .queue import snapshot

    return snapshot()


from .ai_api import router as ai_router  # noqa: E402
from .context_api import router as context_router  # noqa: E402
from .git_source_api import router as git_source_router  # noqa: E402
from .orchestration_settings import router as orchestration_router  # noqa: E402
from .question_api import router as question_router  # noqa: E402
from .ticket_api import router as ticket_router  # noqa: E402

api.add_router("", question_router)
api.add_router("", context_router)
api.add_router("", ticket_router)
api.add_router("", git_source_router)
api.add_router("", ai_router)
api.add_router("", orchestration_router)
