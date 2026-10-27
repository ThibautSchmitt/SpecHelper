"""Ticket connector administration and explicitly confirmed publication endpoints."""

import math
from datetime import timedelta
from typing import Literal
from uuid import UUID

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field, field_validator

from .models import (
    Environment,
    PublishedTicket,
    Request,
    ResultVersion,
    TicketConnector,
)
from .secrets import decrypt, encrypt
from .ticket_providers import provider_for, render_body
from .ticket_publication import (
    accessible_projects,
    connector_dict,
    preview,
    publication_dict,
    publish,
    safe_provider_error,
    validate_base_url,
)

router = Router(tags=["Ticket publication"])


class StrictSchema(Schema):
    model_config = ConfigDict(extra="forbid")


class ConnectorIn(StrictSchema):
    environment_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    platform: Literal["github", "gitlab", "jira", "glpi"]
    base_url: str = Field(min_length=1, max_length=1000)
    username: str = Field(default="", max_length=255)
    secret: str = Field(default="", max_length=4096)
    app_token: str = Field(default="", max_length=4096)
    api_version: Literal["v1"] = "v1"
    projects: list[str] = Field(default_factory=list, max_length=1000)
    default_project: str = Field(default="", max_length=255)


class PreviewIn(StrictSchema):
    connector_id: int = Field(ge=1)
    project: str = Field(min_length=1, max_length=255)
    template_id: str = Field(default="", max_length=500)
    issue_type: str = Field(default="", max_length=255)
    ticket_format: Literal["", "project", "standard"] = ""
    include_business_analysis: bool = False
    include_technical_analysis: bool = False
    include_attachments: bool = False
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)
    include_goal: bool = False
    include_diagrams: bool = False


class PublicationDraftIn(PreviewIn):
    title: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=200000)
    fields: dict[str, str | list[str] | int | float | bool | None] = Field(
        default_factory=dict, max_length=100
    )
    labels: list[str] = Field(default_factory=list, max_length=100)
    assignees: list[str] = Field(default_factory=list, max_length=100)
    options_revision: str = Field(min_length=1, max_length=128)
    draft_id: UUID | None = None
    draft_revision: int | None = Field(default=None, ge=1)

    @field_validator("fields")
    @classmethod
    def bound_field_values(cls, fields):
        if len(str(fields)) > 200000:
            raise ValueError("Ticket field values are too large")
        if any(isinstance(value, float) and not math.isfinite(value) for value in fields.values()):
            raise ValueError("Ticket field values must be finite numbers")
        return fields


class PublicationIn(PublicationDraftIn):
    title: str = Field(min_length=1, max_length=500)
    idempotency_key: UUID
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit human confirmation is required")
        return value


def connector_values(payload, existing=None):
    values = payload.model_dump(exclude={"secret", "app_token"})
    get_object_or_404(Environment, pk=payload.environment_id)
    if existing and existing.environment_id not in {None, payload.environment_id}:
        raise HttpError(409, "Create a new connector to use a different environment.")
    values["base_url"] = validate_base_url(values["base_url"])
    projects = values["projects"]
    if any(not item or len(item) > 255 for item in projects) or len(set(projects)) != len(projects):
        raise HttpError(422, "Enter unique project identifiers of at most 255 characters.")
    if values["default_project"] and values["default_project"] not in projects:
        raise HttpError(422, "The default project must be allowed by this connector.")
    for key in ("secret", "app_token"):
        value = getattr(payload, key)
        if value:
            values[key] = encrypt(value)
        elif existing is None:
            values[key] = ""
    from .sensitive_data import git_credentials

    candidate = payload.secret or (existing.secret and decrypt(existing.secret) if existing else "")
    if not candidate:
        raise HttpError(422, "Configure a dedicated ticket publication credential.")
    if candidate in git_credentials():
        raise HttpError(
            422, "Ticket publication must use a credential distinct from Git source access."
        )
    if existing and payload.platform != existing.platform:
        raise HttpError(422, "Create a new connector to change its platform.")
    if existing and values["base_url"] != existing.base_url and existing.published_tickets.exists():
        raise HttpError(
            409,
            "Create a new connector to change the URL of a destination with publication history.",
        )
    values.update(status="UNKNOWN", error="")
    return values


@router.get("/ticket-connectors")
def list_connectors(request, environment_id: int | None = None, request_id: UUID | None = None):
    values = TicketConnector.objects.order_by("name", "id")
    if request_id is not None:
        item = get_object_or_404(Request, pk=request_id)
        if item.environment_id is None:
            return []
        values = values.filter(environment_id=item.environment_id)
    if environment_id is not None:
        get_object_or_404(Environment, pk=environment_id)
        values = values.filter(environment_id=environment_id)
    return [connector_dict(value) for value in values]


@router.post("/ticket-connectors")
def create_connector(request, payload: ConnectorIn):
    return connector_dict(TicketConnector.objects.create(**connector_values(payload)))


@router.put("/ticket-connectors/{connector_id}")
def update_connector(request, connector_id: int, payload: ConnectorIn):
    connector = get_object_or_404(TicketConnector, pk=connector_id)
    values = connector_values(payload, connector)
    for name, value in values.items():
        setattr(connector, name, value)
    connector.save()
    return connector_dict(connector)


@router.delete("/ticket-connectors/{connector_id}")
def delete_connector(request, connector_id: int):
    connector = get_object_or_404(TicketConnector, pk=connector_id)
    if connector.published_tickets.exists():
        raise HttpError(409, "This connector has publication history and cannot be deleted.")
    connector.delete()
    return {"status": "DELETED"}


@router.post("/ticket-connectors/{connector_id}/test")
def test_connector(request, connector_id: int):
    connector = get_object_or_404(TicketConnector, pk=connector_id)
    try:
        provider_for(connector).test()
    except Exception as exc:
        connector.status = "ERROR"
        connector.error = safe_provider_error(exc)
    else:
        connector.status = "CONNECTED"
        connector.error = ""
    connector.save(update_fields=["status", "error", "updated_at"])
    return connector_dict(connector)


@router.get("/ticket-connectors/{connector_id}/projects")
def connector_projects(request, connector_id: int):
    return accessible_projects(get_object_or_404(TicketConnector, pk=connector_id))


@router.get("/tickets")
def list_tickets(
    request,
    platform: str = "",
    environment: str = "",
    search: str = "",
    page: int = 1,
    status: str = "PUBLISHED",
):
    if status not in {"all", *PublishedTicket.Status.values}:
        raise HttpError(422, "Unknown ticket publication status.")
    values = PublishedTicket.objects.all().select_related("connector", "version")
    environments = list(
        values.order_by("version__environment_name")
        .values_list("version__environment_name", flat=True)
        .distinct()
    )
    stale = Q(status="PUBLISHING", updated_at__lt=timezone.now() - timedelta(seconds=90))
    if status == "UNCERTAIN":
        values = values.filter(Q(status="UNCERTAIN") | stale)
    elif status == "PUBLISHING":
        values = values.filter(status=status).exclude(stale)
    elif status != "all":
        values = values.filter(status=status)
    if platform:
        values = values.filter(platform=platform)
    if environment:
        values = values.filter(version__environment_name=environment)
    if search:
        values = values.filter(
            Q(title__icontains=search[:500])
            | Q(external_key__icontains=search[:500])
            | Q(project__icontains=search[:500])
        )
    page = max(1, page)
    size = 25
    return {
        "items": [publication_dict(value) for value in values[(page - 1) * size : page * size]],
        "total": values.count(),
        "page": page,
        "page_size": size,
        "environments": environments,
        "statuses": PublishedTicket.Status.values,
    }


@router.get("/tickets/{ticket_id}")
def ticket_detail(request, ticket_id: UUID):
    value = get_object_or_404(
        PublishedTicket.objects.select_related("connector", "version"), pk=ticket_id
    )
    labels = value.snapshot.get("labels", [])
    return {
        **publication_dict(value),
        "description": value.body,
        "labels": [label for label in labels if isinstance(label, str)]
        if isinstance(labels, list)
        else [],
        "payload_available": True,
    }


@router.get("/requests/{request_id}/versions/{number}/publications")
def version_publications(request, request_id: UUID, number: int):
    version = get_object_or_404(
        ResultVersion, request_id=request_id, number=number, request__workflow="request"
    )
    return [
        publication_dict(value)
        for value in version.published_tickets.select_related("connector", "version")
    ]


@router.post("/requests/{request_id}/versions/{number}/publication-preview")
def publication_preview(request, request_id: UUID, number: int, payload: PreviewIn):
    version = get_object_or_404(
        ResultVersion, request_id=request_id, number=number, request__workflow="request"
    )
    connector = get_object_or_404(TicketConnector, pk=payload.connector_id)
    return preview(
        version,
        connector,
        payload.project,
        payload.template_id,
        payload.issue_type,
        payload.model_dump(mode="json"),
    )


@router.get("/requests/{request_id}/versions/{number}/publication-draft")
def publication_draft(request, request_id: UUID, number: int, connector_id: int, project: str):
    from .models import TicketPublicationDraft

    version = get_object_or_404(
        ResultVersion, request_id=request_id, number=number, request__workflow="request"
    )
    connector = get_object_or_404(TicketConnector, pk=connector_id)
    draft = TicketPublicationDraft.objects.filter(
        version=version, connector=connector, project=project
    ).first()
    presentation = (
        draft.presentation
        if draft
        else PreviewIn(connector_id=connector_id, project=project).model_dump(mode="json")
    )
    return preview(
        version,
        connector,
        project,
        presentation.get("template_id", ""),
        presentation.get("issue_type", ""),
        presentation,
        restore=True,
    )


@router.put("/requests/{request_id}/versions/{number}/publication-draft")
def update_publication_draft(request, request_id: UUID, number: int, payload: PublicationDraftIn):
    from .models import TicketPublicationDraft
    from .ticket_presentation import (
        PRESENTATION_KEYS,
        draft_metadata,
        publication_reference,
        save_draft,
    )

    version = get_object_or_404(
        ResultVersion, request_id=request_id, number=number, request__workflow="request"
    )
    connector = get_object_or_404(TicketConnector, pk=payload.connector_id)
    previous = TicketPublicationDraft.objects.filter(
        version=version, connector=connector, project=payload.project
    ).first()
    if payload.draft_revision is not None and (
        previous is None or previous.revision != payload.draft_revision
    ):
        raise HttpError(409, "The ticket draft changed. Reload it before saving your edits.")
    values = payload.model_dump(mode="json")
    result = preview(
        version,
        connector,
        payload.project,
        payload.template_id,
        payload.issue_type,
        values,
        restore=True,
    )
    if values["options_revision"] != result["revision"]:
        raise HttpError(
            409,
            "The destination options or template changed. Review the publication preview again.",
        )
    content = {
        key: values[key]
        for key in ("title", "body", "fields", "labels", "assignees", "options_revision")
    }
    content["selected_attachments"] = result["selected_attachments"]
    presentation = {key: result[key] for key in PRESENTATION_KEYS}
    draft = save_draft(
        version,
        connector,
        payload.project,
        presentation,
        content,
        expected_revision=result["draft_revision"],
    )
    return {
        **result,
        "title": content["title"],
        "body": content["body"],
        "defaults": {
            **result.get("defaults", {}),
            "labels": content["labels"],
            "assignees": content["assignees"],
        },
        "values": content["fields"],
        **draft_metadata(draft, version),
        "publication_reference": publication_reference(draft),
        "rendered_body": render_body(content, result, publication_reference(draft)),
    }


@router.post("/requests/{request_id}/versions/{number}/publications")
def create_publication(request, request_id: UUID, number: int, payload: PublicationIn):
    version = get_object_or_404(
        ResultVersion, request_id=request_id, number=number, request__workflow="request"
    )
    connector = get_object_or_404(TicketConnector, pk=payload.connector_id)
    values = payload.model_dump(mode="json")
    if "ticket_format" not in payload.model_fields_set:
        # Historical publication snapshots predate presentation options. Schema
        # defaults must not change their digest during read-only reconciliation.
        from .ticket_presentation import PRESENTATION_KEYS

        for key in PRESENTATION_KEYS:
            if key not in {"template_id", "issue_type"}:
                values.pop(key, None)
    return publication_dict(publish(version, connector, values))
