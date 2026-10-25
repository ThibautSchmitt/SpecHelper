"""Selectable model metadata with identity-scoped, honestly bounded availability evidence."""

from typing import Literal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field

from .agent import runtime_call
from .models import AIConnection, AIModel, AIModelDiscovery, AIModelObservation
from .providers import identity_for, runtime_identity

router = Router(tags=["AI models"])
Agent = Literal["codex", "claude", "antigravity"]
IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$"


class ModelIn(Schema):
    model_config = ConfigDict(extra="forbid")
    agent: Agent
    identifier: str = Field(min_length=1, max_length=100, pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    family: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9._-]*$")


class ModelPatch(Schema):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    family: str | None = Field(default=None, max_length=100, pattern=r"^[a-zA-Z0-9._-]*$")
    enabled: bool | None = None


def public(model, identity=None):
    observation = model.observations.filter(identity=identity).first() if identity else None
    return {
        "id": model.pk,
        "agent": model.agent,
        "identifier": model.identifier,
        "name": model.name,
        "family": model.family
        or {"codex": "openai", "claude": "anthropic", "antigravity": "google"}.get(
            model.agent, model.agent
        ),
        "source": model.source,
        "enabled": model.enabled,
        "status": observation.status if observation else "UNKNOWN",
        "reason": observation.reason if observation else "not_verified",
        "checked_at": observation.checked_at if observation else None,
    }


def list_catalog(agent=None, connection=None):
    identity = identity_for(connection) if connection else None
    if connection and agent is not None and connection.agent != agent:
        raise HttpError(422, "The model provider must match the connection.")
    agent = connection.agent if connection else agent
    # Legacy explicit identifiers are retained as unverified, never silently replaced.
    for configured in AIConnection.objects.exclude(model="").filter(
        **({"agent": agent} if agent else {})
    ):
        AIModel.objects.get_or_create(
            agent=configured.agent,
            identifier=configured.model,
            defaults={"name": configured.model, "source": "configured"},
        )
    rows = AIModel.objects.filter(**({"agent": agent} if agent else {})).order_by(
        "agent", "name", "id"
    )
    discovery = AIModelDiscovery.objects.filter(identity=identity).first() if identity else None
    return {
        "items": [public(model, identity) for model in rows],
        "discovery": {
            "state": discovery.state,
            "reason": discovery.reason,
            "checked_at": discovery.checked_at,
        }
        if discovery
        else {"state": "unknown", "reason": "not_refreshed", "checked_at": None},
    }


def validate_model(agent, model):
    if not model:
        return
    option = AIModel.objects.filter(agent=agent, identifier=model, enabled=True).first()
    if option is None:
        raise HttpError(
            422,
            "Select an enabled model from the provider catalog or add an administered model first.",
        )


@router.get("/ai-models")
def list_models(request, agent: Agent | None = None, connection_id: int | None = None):
    connection = (
        get_object_or_404(AIConnection, pk=connection_id) if connection_id is not None else None
    )
    return list_catalog(agent, connection)


@router.post("/ai-models")
@transaction.atomic
def add_model(request, payload: ModelIn):
    from .environment_context import reject_credentials

    reject_credentials(payload.name)
    reject_credentials(payload.identifier)
    reject_credentials(payload.family)
    if not payload.name.strip():
        raise HttpError(422, "Enter a model name.")
    if AIModel.objects.filter(agent=payload.agent, identifier=payload.identifier).exists():
        raise HttpError(409, "This provider model is already registered.")
    return public(AIModel.objects.create(**{**payload.model_dump(), "name": payload.name.strip()}))


@router.put("/ai-models/{model_id}")
@transaction.atomic
def update_model(request, model_id: int, payload: ModelPatch):
    item = get_object_or_404(AIModel.objects.select_for_update(), pk=model_id)
    values = payload.model_dump(exclude_unset=True)
    if "family" in values:
        from .environment_context import reject_credentials

        reject_credentials(values["family"] or "")
    if any(value is None for value in values.values()):
        raise HttpError(422, "Model fields cannot be null.")
    if "name" in values:
        from .environment_context import reject_credentials

        reject_credentials(values["name"])
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise HttpError(422, "Enter a model name.")
    for name, value in values.items():
        setattr(item, name, value)
    item.save()
    return public(item)


def refresh(connection):
    from .ai_api import not_processing

    not_processing(connection)
    identity = identity_for(connection)
    credential_id = runtime_identity(connection)
    path = (
        "/models?agent="
        + connection.agent
        + ("&identity_id=" + credential_id if credential_id else "")
    )
    try:
        data = runtime_call(path, timeout=15)
        if data.get("state") not in {"supported", "unavailable", "error"}:
            raise ValueError("Invalid model discovery response")
        reason = data.get("reason")
        if reason not in {
            "unsupported_cli",
            "not_connected",
            "catalog_not_entitlement",
            "refresh_failed",
        }:
            raise ValueError("Invalid model discovery reason")
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) > 1000:
            raise ValueError("Invalid model discovery catalog")
        parsed = [ModelIn.model_validate({**item, "agent": connection.agent}) for item in items]
        with transaction.atomic():
            AIModelDiscovery.objects.update_or_create(
                identity=identity, defaults={"state": data["state"], "reason": reason}
            )
            if data["state"] == "supported":
                present = set()
                for item in parsed:
                    model, _ = AIModel.objects.get_or_create(
                        agent=connection.agent,
                        identifier=item.identifier,
                        defaults={"name": item.name, "family": item.family, "source": "adapter"},
                    )
                    if item.family and not model.family:
                        model.family = item.family
                        model.save(update_fields=["family"])
                    present.add(model.pk)
                    previous = (
                        AIModelObservation.objects.select_for_update()
                        .filter(model=model, identity=identity)
                        .first()
                    )
                    # A metadata refresh does not erase a successful invocation as weaker evidence.
                    if not previous or previous.status != "AVAILABLE":
                        AIModelObservation.objects.update_or_create(
                            model=model,
                            identity=identity,
                            defaults={"status": "SUPPORTED", "reason": "catalog_not_entitlement"},
                        )
                AIModelObservation.objects.filter(identity=identity).exclude(
                    model_id__in=present
                ).update(
                    status="UNKNOWN", reason="not_in_latest_catalog", checked_at=timezone.now()
                )
    except (ValueError, OSError, TypeError, AttributeError):
        AIModelDiscovery.objects.update_or_create(
            identity=identity, defaults={"state": "error", "reason": "refresh_failed"}
        )
    return list_catalog(connection=connection)


@router.post("/ai-connections/{connection_id}/models/refresh")
def refresh_models(request, connection_id: int):
    return refresh(get_object_or_404(AIConnection, pk=connection_id))


@router.post("/ai-connections/{connection_id}/models/{model_id}/test")
def test_model(request, connection_id: int, model_id: int):
    connection = get_object_or_404(AIConnection, pk=connection_id)
    model = get_object_or_404(AIModel, pk=model_id, agent=connection.agent, enabled=True)
    refresh(connection)
    return {
        "model": public(model, identity_for(connection)),
        "inference_performed": False,
        "access_verified": False,
    }


def record_execution(connection, identifier, available):
    """Only an actual analysis success/model rejection provides entitlement evidence."""
    if not identifier:
        return
    model, _ = AIModel.objects.get_or_create(
        agent=connection.agent,
        identifier=identifier,
        defaults={"name": identifier, "source": "configured"},
    )
    AIModelObservation.objects.update_or_create(
        model=model,
        identity=identity_for(connection),
        defaults={
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "reason": "successful_analysis" if available else "model_rejected",
        },
    )
