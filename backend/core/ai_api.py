"""Administration of named terminal configurations without credential disclosure."""

import re
import uuid
from typing import Literal

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field, SecretStr, field_validator

from .agent import runtime_call
from .connections import ACTIVE, start
from .models import AIConnection, AIIdentity, AISession, ConnectionAttempt
from .orchestration_settings import Role, validate_connection_overrides
from .providers import (
    ensure_connections,
    identity_for,
    model_pool_exhausted,
    model_quota_pool,
    observe,
    public,
    quota_group,
    runtime_identity,
)

router = Router(tags=["AI connections"])


class ConfigurationIn(Schema):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    agent: Literal["codex", "claude", "antigravity"]
    model: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$|^$")
    enabled: bool = True
    is_default: bool = False
    preference: int = Field(default=100, ge=0, le=2147483647)
    share_identity_from: int | None = None
    roles: list[Role] = Field(default_factory=lambda: ["analyst", "counter_analyst", "verifier"])
    additional_instructions: str = Field(default="", max_length=12000)
    skill_overrides: dict[str, bool] = Field(default_factory=dict)


class ConfigurationPatch(Schema):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    agent: Literal["codex", "claude", "antigravity"] | None = None
    model: str | None = Field(
        default=None, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$|^$"
    )
    enabled: bool | None = None
    is_default: bool | None = None
    preference: int | None = Field(default=None, ge=0, le=2147483647)
    roles: list[Role] | None = None
    additional_instructions: str | None = Field(default=None, max_length=12000)
    skill_overrides: dict[str, bool] | None = None


class APIKeyAuthenticationIn(Schema):
    """Explicit billed-provider opt-in; never inherited from the host environment."""

    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=16, max_length=256)
    confirm_billing: Literal[True]

    @field_validator("api_key")
    @classmethod
    def bounded_api_key(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", value.get_secret_value()):
            raise ValueError("Enter a supported API key without spaces or control characters.")
        return value

    @field_validator("confirm_billing", mode="before")
    @classmethod
    def explicit_billing_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit API billing consent is required.")
        return value


def not_processing(connection):
    identity = identity_for(connection)
    if quota_group(identity).filter(availability="BUSY", retry_after__isnull=True).exists():
        raise HttpError(409, "This assistant is processing a request. Retry after the result.")
    if ConnectionAttempt.objects.filter(identity=identity, status__in=ACTIVE).exists():
        raise HttpError(409, "A connection is already in progress")


@router.get("/ai-connections")
def list_connections(request):
    return [public(value) for value in ensure_connections()]


@router.post("/ai-connections")
@transaction.atomic
def create_connection(request, payload: ConfigurationIn):
    from .model_catalog import validate_model

    validate_model(payload.agent, payload.model)
    validate_connection_overrides(payload.roles, payload.skill_overrides)
    values = payload.model_dump(exclude={"share_identity_from"})
    values["name"] = values["name"].strip()
    if not values["name"]:
        raise HttpError(422, "Enter an AI connection name")
    if payload.share_identity_from is not None:
        source = get_object_or_404(AIConnection, pk=payload.share_identity_from)
        if source.agent != payload.agent:
            raise HttpError(422, "A shared identity must use the same provider")
        identity = identity_for(source)
    else:
        identity = AIIdentity.objects.create(agent=payload.agent, credential_id=uuid.uuid4())
    if payload.is_default:
        list(AIConnection.objects.select_for_update().order_by("id"))
        AIConnection.objects.update(is_default=False)
    value = AIConnection.objects.create(
        **values,
        identity=identity,
        status=identity.status,
        account=identity.account,
        availability=identity.availability,
        checked_at=identity.checked_at,
    )
    return public(value)


@router.put("/ai-connections/{connection_id}")
@transaction.atomic
def edit_connection(request, connection_id: int, payload: ConfigurationPatch):
    value = get_object_or_404(AIConnection.objects.select_for_update(), pk=connection_id)
    not_processing(value)
    identity = identity_for(value)
    previous_pool = model_quota_pool(value)
    previous_pool_exhausted = model_pool_exhausted(value, identity)
    values = payload.model_dump(exclude_unset=True)
    if "model" in values and values["model"] != value.model:
        from .model_catalog import validate_model

        validate_model(value.agent, values["model"])
    validate_connection_overrides(values.get("roles"), values.get("skill_overrides"))
    if any(item is None for item in values.values()):
        raise HttpError(422, "Configuration fields cannot be null")
    if "agent" in values and values.pop("agent") != value.agent:
        raise HttpError(422, "The provider cannot be changed. Create another connection.")
    if "name" in values:
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise HttpError(422, "Enter an AI connection name")
    if values.get("is_default"):
        list(AIConnection.objects.select_for_update().order_by("id"))
        AIConnection.objects.exclude(pk=value.pk).update(is_default=False)
    if "model" in values and value.availability == "MODEL_UNAVAILABLE":
        values["availability"] = "UNKNOWN"
    for key, item in values.items():
        setattr(value, key, item)
    if (
        value.availability == "QUOTA_EXHAUSTED"
        and previous_pool_exhausted
        and identity.availability in {"AVAILABLE", "UNKNOWN"}
        and model_quota_pool(value)
        and model_quota_pool(value) != previous_pool
    ):
        value.availability = "UNKNOWN"
    value.save()
    return public(value)


@router.delete("/ai-connections/{connection_id}")
@transaction.atomic
def delete_connection(request, connection_id: int):
    value = get_object_or_404(AIConnection.objects.select_for_update(), pk=connection_id)
    not_processing(value)
    if AISession.objects.filter(connection=value).exists():
        raise HttpError(409, "This AI connection has analysis history. Disable it instead.")
    try:
        value.delete()
    except ProtectedError as exc:
        raise HttpError(409, "This AI connection is still referenced. Disable it instead.") from exc
    return {"deleted": True}


def test_configuration(value):
    not_processing(value)
    credential_id = runtime_identity(value)
    path = (
        "/health?agent="
        + value.agent
        + ("&identity_id=" + credential_id if credential_id else "")
        + "&quota=true"
    )
    try:
        return observe(value, runtime_call(path, timeout=25))
    except ValueError as exc:
        raise HttpError(
            503, "The connection service is not responding. Try again shortly."
        ) from exc


@router.post("/ai-connections/{connection_id}/test")
def test_connection(request, connection_id: int):
    return test_configuration(get_object_or_404(AIConnection, pk=connection_id))


@router.post("/ai-connections/{connection_id}/quota/refresh")
@transaction.atomic
def refresh_quota(request, connection_id: int):
    """Read provider metadata at most every two minutes per shared identity.

    Row locks coordinate browsers and application processes. Competing refreshes
    return the last observation immediately, without launching an inference or
    blocking an active analysis. Failed reads never replace valid observations.
    """
    value = get_object_or_404(AIConnection, pk=connection_id)
    identity = identity_for(value)
    ids = list(quota_group(identity).order_by("pk").values_list("pk", flat=True))
    locked = list(
        AIIdentity.objects.select_for_update(skip_locked=True).filter(pk__in=ids).order_by("pk")
    )
    if len(locked) != len(ids) or not value.enabled:
        return {**public(value), "quota_refresh_state": "pending"}
    if any(item.availability == "BUSY" for item in locked):
        return {**public(value), "quota_refresh_state": "busy"}
    observations = []
    for item in locked:
        status = (
            item.quota_windows.get("_status", {}) if isinstance(item.quota_windows, dict) else {}
        )
        try:
            checked = parse_datetime(status.get("checked_at", ""))
        except (TypeError, ValueError):
            checked = None
        if checked and timezone.is_aware(checked):
            observations.append(checked)
    if observations and (timezone.now() - max(observations)).total_seconds() < 120:
        return {**public(value), "quota_refresh_state": "cached"}
    try:
        return {**test_configuration(value), "quota_refresh_state": "refreshed"}
    except HttpError as error:
        if error.status_code != 503:
            raise
        for item in locked:
            windows = item.quota_windows if isinstance(item.quota_windows, dict) else {}
            AIIdentity.objects.filter(pk=item.pk).update(
                quota_windows={
                    **windows,
                    "_status": {
                        "state": "error",
                        "reason": "refresh_failed",
                        "checked_at": timezone.now().isoformat(),
                    },
                }
            )
        value.refresh_from_db()
        return {**public(value), "quota_refresh_state": "error"}


@router.post("/ai-connections/{connection_id}/auth/start")
def start_connection(request, connection_id: int):
    value = get_object_or_404(AIConnection, pk=connection_id)
    return start(value.agent, identity_id=identity_for(value).pk)


@router.post("/ai-connections/{connection_id}/auth/api-key")
@transaction.atomic
def configure_api_key(request, connection_id: int, payload: APIKeyAuthenticationIn):
    """Send an explicitly approved key directly to the trusted encrypted runtime vault.

    The backend stores neither the key nor an authentication request payload. Saving
    credentials does not run inference or prove access to the selected model.
    """
    value = get_object_or_404(AIConnection.objects.select_for_update(), pk=connection_id)
    if value.agent != "antigravity":
        raise HttpError(422, "API-key authentication is available only for Antigravity.")
    not_processing(value)
    identity = AIIdentity.objects.select_for_update().get(pk=identity_for(value).pk)
    if identity.credential_id is None:
        identity.credential_id = uuid.uuid4()
        identity.save(update_fields=["credential_id"])
    try:
        state = runtime_call(
            "/auth/api-key",
            {
                "provider": "antigravity",
                "identity_id": str(identity.credential_id),
                "api_key": payload.api_key.get_secret_value(),
                "confirm_billing": True,
            },
            timeout=25,
        )
    except ValueError as exc:
        raise HttpError(
            503, "The connection service is not responding. Try again shortly."
        ) from exc
    from .sensitive_data import redact

    state = redact(state, [payload.api_key.get_secret_value()])
    return {
        **observe(value, state),
        "authentication_mode": "api_key",
        "access_verified": False,
    }
