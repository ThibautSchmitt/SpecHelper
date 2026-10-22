"""Administration of independent, read-only source credentials."""

from typing import Literal

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field

from .git_sources import Provider, SourceError, base_url, connection_dict, fail_connection
from .models import (
    ConnectionAttempt,
    EnvironmentRepository,
    GitConnection,
    GitHubConnection,
    Request,
)
from .secrets import encrypt

router = Router(tags=["Git sources"])


class ConnectionIn(Schema):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    provider: Literal["github", "gitlab"]
    base_url: str = Field(default="https://github.com", max_length=1000)
    secret: str = Field(default="", max_length=4096)
    enabled: bool = True
    import_github: bool = False


def values(payload, existing=None):
    result = payload.model_dump(exclude={"secret", "import_github"})
    result["name"] = result["name"].strip()
    if not result["name"]:
        raise HttpError(422, "Enter a connection name.")
    result["base_url"] = base_url(payload.provider, payload.base_url)
    if existing and (
        existing.provider != payload.provider or existing.base_url != result["base_url"]
    ):
        raise HttpError(409, "Create a new connection to change its Git provider or instance.")
    if payload.secret:
        result["secret"] = encrypt(payload.secret)
    if payload.import_github:
        if payload.provider != "github":
            raise HttpError(422, "Browser GitHub authentication can only be used with GitHub.")
        legacy = GitHubConnection.objects.filter(pk=1).first()
        if not legacy or not legacy.secret:
            raise HttpError(422, "Connect with GitHub before importing this browser authorization.")
        result.update(secret=legacy.secret, account=legacy.account)
    if not existing and not result.get("secret"):
        result["secret"] = ""
    if "secret" in result or not existing:
        result.update(status="UNKNOWN", error="")
    return result


@router.get("/git-connections")
def connections(request):
    return [connection_dict(value) for value in GitConnection.objects.order_by("name", "id")]


@router.post("/git-connections")
def create(request, payload: ConnectionIn):
    return connection_dict(GitConnection.objects.create(**values(payload)))


@router.put("/git-connections/{connection_id}")
def update(request, connection_id: int, payload: ConnectionIn):
    connection = get_object_or_404(GitConnection, pk=connection_id)
    for key, value in values(payload, connection).items():
        setattr(connection, key, value)
    connection.save()
    return connection_dict(connection)


@router.delete("/git-connections/{connection_id}")
@transaction.atomic
def delete(request, connection_id: int, confirm_name: str = ""):
    connection = get_object_or_404(GitConnection.objects.select_for_update(), pk=connection_id)
    repository_ids = set(connection.repositories.values_list("id", flat=True))
    historical = any(
        any(
            row.get("git_repository_id") in repository_ids
            or (connection.legacy_source and not row.get("git_repository_id"))
            for row in baseline
        )
        for baseline in Request.objects.values_list("baseline", flat=True).iterator()
    )
    legacy_referenced = (
        connection.legacy_source
        and EnvironmentRepository.objects.filter(git_repository__isnull=True).exists()
    )
    if (
        historical
        or legacy_referenced
        or connection.repositories.filter(environment_repositories__isnull=False).exists()
    ):
        if confirm_name != connection.name:
            raise HttpError(
                409,
                "This connection is referenced. Confirm its exact name to disable it while preserving environments and history.",
            )
        connection.enabled = False
        connection.save(update_fields=["enabled", "updated_at"])
        return {"status": "DISABLED"}
    attempts = ConnectionAttempt.objects.select_for_update().filter(git_connection=connection)
    active = attempts.filter(status__in={"STARTING", "AWAITING_USER"})
    if active.filter(expires_at__gt=timezone.now()).exists():
        raise HttpError(
            409,
            "Cancel the active GitHub connection attempt before deleting this source connection.",
        )
    # Terminal attempts remain audit records. Expired processes must observe cancellation
    # before their target is detached, so a late callback cannot authorize the singleton.
    active.update(status="CANCELLED", input_required=False, message="Connection cancelled.")
    attempts.update(git_connection=None)
    try:
        connection.repositories.all().delete()
        connection.delete()
    except ProtectedError as exc:
        raise HttpError(
            409, "This Git connection is still referenced and cannot be deleted."
        ) from exc
    return {"status": "DELETED"}


@router.post("/git-connections/{connection_id}/test")
def test(request, connection_id: int):
    connection = get_object_or_404(GitConnection, pk=connection_id)
    try:
        connection.account = Provider(connection).test()
    except SourceError as exc:
        connection.status, connection.error = "ERROR", str(exc)
    else:
        connection.status, connection.error = "CONNECTED", ""
    connection.checked_at = timezone.now()
    connection.save(update_fields=["account", "status", "error", "checked_at", "updated_at"])
    return connection_dict(connection)


def discover(connection_id, search, page, page_size, remote_id=None):
    connection = get_object_or_404(GitConnection, pk=connection_id)
    page, page_size = max(1, page), max(1, min(100, page_size))
    try:
        provider = Provider(connection)
        if remote_id is None:
            items, more = provider.projects(search[:200], page, page_size)
        else:
            source = provider.project(remote_id)
            items, more = provider.branches(source, search[:200], page, page_size)
    except SourceError as exc:
        fail_connection(connection, exc)
        raise HttpError(422, str(exc)) from exc
    GitConnection.objects.filter(pk=connection.pk).update(
        status="CONNECTED", error="", checked_at=timezone.now()
    )
    return {"items": items, "page": page, "page_size": page_size, "has_more": more}


@router.get("/git-connections/{connection_id}/projects")
def projects(request, connection_id: int, search: str = "", page: int = 1, page_size: int = 30):
    return discover(connection_id, search, page, page_size)


@router.get("/git-connections/{connection_id}/branches")
def branches(
    request,
    connection_id: int,
    remote_id: str,
    search: str = "",
    page: int = 1,
    page_size: int = 30,
):
    return discover(connection_id, search, page, page_size, remote_id)


@router.post("/git-connections/{connection_id}/auth/start")
def start_auth(request, connection_id: int):
    from . import connections

    connection = get_object_or_404(GitConnection, pk=connection_id)
    if connection.provider != "github":
        raise HttpError(422, "Use a read-only access token for this GitLab instance.")
    return connections.start("github", git_connection_id=connection.id)
