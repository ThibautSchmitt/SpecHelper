"""Ticket connector administration and explicitly confirmed publication endpoints."""

import math
from typing import Literal
from uuid import UUID

from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field, field_validator

from .models import (
    ConversationTicket,
    Environment,
    PublishedTicket,
    Request,
    TicketConnector,
    TicketPublicationDraft,
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


class RemovePublicationIn(Schema):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(default=False, strict=True)


@router.delete("/tickets/{ticket_id}")
def remove_published_ticket(request, ticket_id: UUID, payload: RemovePublicationIn):
    from .local_deletion import remove_publication
    if payload.confirmed is not True:
        raise HttpError(422, "Confirm removal of this ticket from SpecHelper.")
    return remove_publication(ticket_id)


@router.get("/analyses/{analysis_id}/versions/{number}/reports/{kind}")
def analysis_report(request, analysis_id: UUID, number: int, kind: Literal["business", "technical"]):
    from .deliverables import result_report
    return result_report(analysis_id, number, kind)


@router.get("/analyses/{analysis_id}/runs/{number}/reports/{kind}")
def partial_analysis_report(request, analysis_id: UUID, number: int, kind: Literal["business", "technical"]):
    from .deliverables import interrupted_report
    return interrupted_report(analysis_id, number, kind)


@router.get("/analyses/{analysis_id}/goal")
def analysis_goal(request, analysis_id: UUID, ticket_id: UUID | None = None, source_version: int | None = None, generation_id: int | None = None):
    if generation_id is not None:
        from .goal_generation import result
        get_object_or_404(Request, pk=analysis_id, deleted_at__isnull=True)
        return result(analysis_id, generation_id)
    from .deliverables import goal_document
    return goal_document(analysis_id, ticket_id, source_version)


@router.post("/analyses/{analysis_id}/goal/generate")
def generate_goal(request, analysis_id: UUID, ticket_id: UUID | None = None, source_version: int | None = None, connection_id: int | None = None):
    from .discussion_access import actor
    from .goal_generation import generate
    return generate(analysis_id, actor(request), ticket_id, source_version, connection_id)


@router.get("/analyses/{analysis_id}/goal/assistants")
def goal_assistants(request, analysis_id: UUID):
    from .discussion_continuation import option
    from .providers import candidates
    get_object_or_404(Request,pk=analysis_id,deleted_at__isnull=True)
    return [option(connection) for connection in candidates() if "analyst" in connection.roles]


class StrictSchema(Schema):
    model_config = ConfigDict(extra="forbid")


class ConnectorIn(StrictSchema):
    # Older clients may associate one environment when saving a connection.
    environment_id: int | None = Field(default=None, ge=1)
    enabled: bool = True
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
    conversation_ticket_id: UUID | None = None
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
    document_generations: dict[Literal["goal", "business", "technical"], int] = Field(default_factory=dict, max_length=3)


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
    unverified_confirmed: bool = Field(default=False, strict=True)
    title: str = Field(min_length=1, max_length=500)
    idempotency_key: UUID
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit human confirmation is required")
        return value


class TicketPreparationIn(StrictSchema):
    ticket_id: UUID | None = None
    new_ticket: bool = False
    expected_revision: int = Field(ge=0)
    expected_discussion_revision: int = Field(ge=0)
    source_version: int | None = Field(default=None, ge=1)
    topic_message_id: int | None = Field(default=None, ge=1)
    anchor_message_id: int | None = Field(default=None, ge=1)
    scope_choice: Literal["unknown", "covered", "clarified", "changed"] = "unknown"
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=30000)
    documents: list[Literal["goal", "business", "technical"]] | None = Field(default=None, max_length=3)

    @field_validator("title")
    @classmethod
    def plain_title(cls, value):
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("Enter a nonempty single-line ticket title.")
        return value.strip()


@router.get("/analyses/{analysis_id}/ticket-preparation")
def ticket_preparation(request, analysis_id: UUID, topic_message_id: int | None = None,
                       source_version: int | None = None, ticket_id: UUID | None = None, new_ticket: bool = False, without_analysis: bool = False, anchor_message_id: int | None = None):
    from .ticket_preparation import snapshot

    return snapshot(get_object_or_404(Request, pk=analysis_id, deleted_at__isnull=True), topic_id=topic_message_id,
                    source_number=source_version, ticket_id=ticket_id, new=new_ticket, without_analysis=without_analysis, anchor_id=anchor_message_id)


@router.put("/analyses/{analysis_id}/ticket-preparation")
def save_ticket_preparation(request, analysis_id: UUID, payload: TicketPreparationIn):
    from .ticket_preparation import save

    return save(analysis_id, payload)


class TicketDocumentsIn(StrictSchema):
    draft_id: UUID
    draft_revision: int = Field(ge=1)
    documents: list[Literal["goal", "business", "technical"]] = Field(min_length=1, max_length=3)
    connection_id: int | None = Field(default=None, gt=0)


@router.post("/analyses/{analysis_id}/tickets/{ticket_id}/documents/generate")
def generate_ticket_documents(request, analysis_id: UUID, ticket_id: UUID, payload: TicketDocumentsIn):
    from .discussion_access import actor
    from .ticket_documents import generate
    return generate(analysis_id, ticket_id, payload, actor(request))


@router.get("/analyses/{analysis_id}/tickets/{ticket_id}/documents/{generation_id}")
def ticket_document_result(request, analysis_id: UUID, ticket_id: UUID, generation_id: int):
    from .ticket_documents import result
    get_object_or_404(ConversationTicket, pk=ticket_id, request_id=analysis_id, request__deleted_at__isnull=True)
    value = result(analysis_id, generation_id)
    from .models import Job
    if Job.objects.get(pk=generation_id).payload["goal_generation"]["inputs"]["ticket"]["id"] != str(ticket_id):
        raise HttpError(404, "Ticket documents not found.")
    return value


class TicketDraftGenerationIn(StrictSchema):
    ticket_id: UUID | None = None
    expected_revision: int = Field(ge=0)
    expected_discussion_revision: int = Field(ge=0)
    source_version: int | None = Field(default=None, ge=1)
    topic_message_id: int | None = Field(default=None, ge=1)
    anchor_message_id: int | None = Field(default=None, ge=1)
    purpose: Literal["prepare", "refresh", "replace"] = "refresh"
    replace_confirmed: bool = Field(default=False, strict=True)


@router.post("/analyses/{analysis_id}/ticket-preparation/generate")
def generate_ticket_preparation(request, analysis_id: UUID, payload: TicketDraftGenerationIn):
    from .api import request_dict
    from .discussion_access import actor
    from .ticket_preparation import generate

    return request_dict(generate(analysis_id, payload, actor(request)), full=True)


class TicketProposalIn(StrictSchema):
    ticket_id: UUID
    proposal_id: UUID
    expected_revision: int = Field(ge=1)
    apply: bool = Field(strict=True)
    replace_confirmed: bool = Field(default=False, strict=True)


@router.post("/analyses/{analysis_id}/ticket-preparation/proposal")
def apply_ticket_proposal(request, analysis_id: UUID, payload: TicketProposalIn):
    from .ticket_preparation import decide_proposal

    return decide_proposal(analysis_id, payload)


def connector_values(payload, existing=None):
    values = payload.model_dump(exclude={"secret", "app_token", "environment_id"})
    if payload.environment_id is not None:
        get_object_or_404(Environment, pk=payload.environment_id)
    if existing:
        for key in ("enabled", "username", "api_version", "projects", "default_project"):
            if key not in payload.model_fields_set:
                values[key] = getattr(existing, key)
    values["base_url"] = validate_base_url(values["base_url"])
    if existing and existing.published_tickets.exists():
        from .ticket_urls import same_instance
        if same_instance(values["base_url"], existing.base_url, existing.platform):
            # Keep old destination hashes and recovery URLs stable for an alias edit.
            values["base_url"] = existing.base_url
    projects = values["projects"]
    if any(not item or len(item) > 255 for item in projects) or len(set(projects)) != len(projects):
        raise HttpError(422, "Enter unique project identifiers of at most 255 characters.")
    if projects and values["default_project"] and values["default_project"] not in projects:
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
    credentials_changed = existing is None or any(
        values[key] != getattr(existing, key)
        for key in ("base_url", "username", "api_version")
    ) or any(getattr(payload, key) for key in ("secret", "app_token"))
    if credentials_changed:
        if existing and existing.published_tickets.filter(status__in=["PUBLISHING", "UNCERTAIN"]).exists():
            raise HttpError(409, "Resolve the pending publication before changing its connection credentials.")
        values.update(status="UNKNOWN", error="")
    return values


@router.get("/ticket-connectors")
def list_connectors(request, environment_id: int | None = None, request_id: UUID | None = None):
    values = TicketConnector.objects.prefetch_related("environments").order_by("name", "id")
    if request_id is not None:
        item = get_object_or_404(Request, pk=request_id)
        if item.environment_id is None:
            return []
        values = values.filter(environments__id=item.environment_id)
    if environment_id is not None:
        get_object_or_404(Environment, pk=environment_id)
        values = values.filter(environments__id=environment_id)
    return [connector_dict(value) for value in values]


@router.post("/ticket-connectors")
@transaction.atomic
def create_connector(request, payload: ConnectorIn):
    connector = TicketConnector.objects.create(**connector_values(payload))
    if payload.environment_id is not None:
        connector.environments.add(payload.environment_id)
    return connector_dict(connector)


@router.put("/ticket-connectors/{connector_id}")
@transaction.atomic
def update_connector(request, connector_id: int, payload: ConnectorIn):
    connector = get_object_or_404(TicketConnector.objects.select_for_update(), pk=connector_id)
    values = connector_values(payload, connector)
    for name, value in values.items():
        setattr(connector, name, value)
    connector.save()
    if payload.environment_id is not None:
        connector.environments.add(payload.environment_id)
    return connector_dict(connector)


@router.delete("/ticket-connectors/{connector_id}")
@transaction.atomic
def delete_connector(request, connector_id: int):
    connector = get_object_or_404(TicketConnector.objects.select_for_update(), pk=connector_id)
    if connector.published_tickets.exists():
        raise HttpError(409, "This connector has publication history and cannot be deleted.")
    if connector.environments.exists():
        raise HttpError(409, "Remove this publication connection from its environments before deleting it.")
    connector.delete()
    return {"status": "DELETED"}


@router.post("/ticket-connectors/{connector_id}/test")
def test_connector(request, connector_id: int):
    connector = get_object_or_404(TicketConnector, pk=connector_id)
    if not connector.enabled:
        raise HttpError(409, "Enable this publication connection before testing it.")
    try:
        provider_for(connector).test()
    except Exception as exc:
        unavailable = str(exc) in {
            "Ticket platform network failure; check publication status before retrying",
            "Ticket platform operation exceeded its time limit",
        }
        connector.status = "UNAVAILABLE" if unavailable else "ERROR"
        connector.error = safe_provider_error(exc)
    else:
        connector.status = "CONNECTED"
        connector.error = ""
    connector.checked_at = timezone.now()
    connector.save(update_fields=["status", "error", "checked_at", "updated_at"])
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
    """Local confirmed-publication history; drafts and operational states stay in conversations."""
    if status not in {"all", "DRAFT", *PublishedTicket.Status.values}:
        raise HttpError(422, "Unknown ticket publication status.")
    values = (
        PublishedTicket.objects.filter(status="PUBLISHED", removed_at__isnull=True)
        .filter(Q(external_id__regex=r"\S") | Q(external_key__regex=r"\S"))
        .select_related("connector", "version", "request__environment")
    )
    values = values.annotate(publication_environment=Coalesce("version__environment_name", NullIf("request__environment_name_snapshot", Value("")), "request__environment__name", Value("")))
    environments = list(
        values.exclude(publication_environment="")
        .order_by("publication_environment")
        .values_list("publication_environment", flat=True)
        .distinct()
    )
    # Retain compatibility with older URLs without exposing failed/pending operations here.
    if status not in {"all", "PUBLISHED"}:
        values = values.none()
    if platform:
        values = values.filter(platform=platform)
    if environment:
        values = values.filter(publication_environment=environment)
    if search:
        search = search[:500]
        values = values.filter(
            Q(title__icontains=search)
            | Q(external_key__icontains=search)
            | Q(external_id__icontains=search)
            | Q(platform__icontains=search)
            | Q(project__icontains=search)
        )
    page, size = max(1, page), 25
    values = values.annotate(publication_date=Coalesce("finished_at", "created_at")).order_by(
        "-publication_date", "-created_at", "id"
    )
    return {
        "items": [published_summary(value) for value in values[(page - 1) * size : page * size]],
        "total": values.count(),
        "page": page,
        "page_size": size,
        "environments": environments,
    }


def published_summary(value):
    from .ticket_publication import stored_publication_url

    return {
        "id": str(value.pk),
        "title": value.title,
        "status": "PUBLISHED",
        "platform": value.platform,
        "project": value.project,
        "external_id": value.external_id,
        "external_key": value.external_key,
        "url": stored_publication_url(value),
        "environment_name": value.publication_environment,
        "published_at": value.finished_at or value.created_at,
        "connector_id": value.connector_id,
        "connector_name": value.connector.name,
        "request_id": str(value.request_id),
        "analysis_deleted": bool(value.request.deleted_at),
        "version_number": value.version.number if value.version_id else None,
        "conversation_ticket_id": str(value.conversation_ticket_id)
        if value.conversation_ticket_id
        else None,
    }


def ticket_record(value):
    return {
        **publication_dict(value),
        "kind": "publication",
        "conversation_title": value.request.display_title or value.request.need[:200],
    }


def preparation_dict(value):
    publications = [publication_dict(item) for item in value.publications.filter(removed_at__isnull=True)]
    from .ticket_preparation import publication_state

    state = publication_state(list(value.publications.all()))
    updated = max([value.updated_at, *[item["updated_at"] for item in publications]])
    return {
        "id": str(value.pk),
        "conversation_ticket_id": str(value.pk),
        "kind": "preparation",
        "title": value.draft.get("title", ""),
        "description": value.draft.get("body", ""),
        "external_id": "",
        "external_key": "",
        "url": "",
        "platform": "",
        "project": "",
        "connector_name": "",
        "environment_name": value.request.environment_name_snapshot
        or (value.request.environment.name if value.request.environment_id else ""),
        "request_id": str(value.request_id),
        "analysis_deleted": bool(value.request.deleted_at),
        "conversation_title": value.request.display_title or value.request.need[:200],
        "topic_message_id": value.topic_message_id,
        "subject": value.topic_message.content
        if value.topic_message_id
        else value.draft.get("title", ""),
        "version_number": value.source_version.number if value.source_version_id else None,
        "status": state,
        "created_at": value.created_at,
        "updated_at": updated,
        "error": "",
        "labels": [],
        "payload_available": True,
        "publications": publications,
        "read_only": any(item["status"] != "ERROR" for item in publications),
    }


def destination_draft_dict(value):
    return {
        "id": str(value.pk),
        "kind": "publication_draft",
        "title": value.content.get("title", ""),
        "description": value.content.get("body", ""),
        "status": "DRAFT",
        "platform": value.connector.platform,
        "connector_name": value.connector.name,
        "project": value.project,
        "external_id": "",
        "external_key": "",
        "url": "",
        "error": "",
        "environment_name": value.version.environment_name,
        "request_id": str(value.version.request_id),
        "conversation_title": value.version.request.display_title
        or value.version.request.need[:200],
        "analysis_deleted": bool(value.version.request.deleted_at),
        "version_number": value.version.number,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "labels": value.content.get("labels", []),
        "publications": [],
        "payload_available": True,
    }


@router.get("/tickets/{ticket_id}")
def ticket_detail(request, ticket_id: UUID):
    value = (
        PublishedTicket.objects.select_related("connector", "version", "request")
        .filter(pk=ticket_id)
        .first()
    )
    if value is not None and value.removed_at:
        raise HttpError(404, "Publication removed from SpecHelper.")
    if value is None:
        draft = (
            TicketPublicationDraft.objects.filter(pk=ticket_id, conversation_ticket__isnull=True)
            .select_related("connector", "version__request")
            .first()
        )
        if draft:
            return destination_draft_dict(draft)
    if value is None:
        return preparation_dict(
            get_object_or_404(
                ConversationTicket.objects.select_related(
                    "request__environment", "source_version", "topic_message"
                ).prefetch_related(
                    "publications__connector", "publications__version", "publications__request"
                ),
                pk=ticket_id,
            )
        )
    labels = value.snapshot.get("labels", [])
    return {
        **ticket_record(value),
        "description": value.body,
        "labels": [label for label in labels if isinstance(label, str)]
        if isinstance(labels, list)
        else [],
        "payload_available": True,
    }


@router.get("/requests/{request_id}/versions/{number}/publications")
def version_publications(request, request_id: UUID, number: int, conversation_ticket_id: UUID | None = None):
    from .ticket_preparation import publication_source
    version = publication_source(request_id, number, conversation_ticket_id)
    from .ticket_preparation import publication_ticket
    if conversation_ticket_id:
        publication_ticket(version, conversation_ticket_id)
    return [
        publication_dict(value)
        for value in PublishedTicket.objects.filter(request_id=request_id, version_id=version.pk, conversation_ticket_id=conversation_ticket_id, removed_at__isnull=True).select_related("connector", "version", "request")
    ]


@router.post("/requests/{request_id}/versions/{number}/publication-preview")
def publication_preview(request, request_id: UUID, number: int, payload: PreviewIn):
    from .ticket_preparation import publication_source
    version = publication_source(request_id, number, payload.conversation_ticket_id)
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
def publication_draft(request, request_id: UUID, number: int, connector_id: int, project: str, conversation_ticket_id: UUID | None = None):
    from .models import TicketPublicationDraft
    from .ticket_preparation import publication_source
    version = publication_source(request_id, number, conversation_ticket_id)
    connector = get_object_or_404(TicketConnector, pk=connector_id)
    from .ticket_preparation import publication_ticket
    ticket = publication_ticket(version, conversation_ticket_id)
    draft = TicketPublicationDraft.objects.filter(
        version_id=version.pk, connector=connector, project=project, conversation_ticket=ticket
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
        {**presentation, "conversation_ticket_id":str(ticket.pk) if ticket else None},
        restore=True,
    )


@router.put("/requests/{request_id}/versions/{number}/publication-draft")
def update_publication_draft(request, request_id: UUID, number: int, payload: PublicationDraftIn):
    from .models import TicketPublicationDraft
    from .ticket_preparation import publication_source
    from .ticket_presentation import (
        PRESENTATION_KEYS,
        draft_metadata,
        publication_reference,
        save_draft,
    )
    version = publication_source(request_id, number, payload.conversation_ticket_id)
    connector = get_object_or_404(TicketConnector, pk=payload.connector_id)
    from .ticket_preparation import publication_ticket
    ticket = publication_ticket(version, payload.conversation_ticket_id)
    previous = TicketPublicationDraft.objects.filter(
        version_id=version.pk, connector=connector, project=payload.project, conversation_ticket=ticket
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
    if values.get("document_generations"):
        presentation["document_generations"] = values["document_generations"]
    draft = save_draft(
        version,
        connector,
        payload.project,
        presentation,
        content,
        expected_revision=result["draft_revision"],
        conversation_ticket=ticket,
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
    from .ticket_preparation import publication_source
    version = publication_source(request_id, number, payload.conversation_ticket_id)
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


# Prepared-ticket routes reuse the same validation, previews and idempotent publication engine.
@router.get("/analyses/{analysis_id}/tickets/{ticket_id}/publications")
def prepared_publications(request, analysis_id: UUID, ticket_id: UUID):
    return version_publications(request, analysis_id, None, ticket_id)


@router.get("/analyses/{analysis_id}/tickets/{ticket_id}/publication-draft")
def prepared_publication_draft(request, analysis_id: UUID, ticket_id: UUID, connector_id: int, project: str):
    return publication_draft(request, analysis_id, None, connector_id, project, ticket_id)


@router.put("/analyses/{analysis_id}/tickets/{ticket_id}/publication-draft")
def update_prepared_publication_draft(request, analysis_id: UUID, ticket_id: UUID, payload: PublicationDraftIn):
    return update_publication_draft(request, analysis_id, None, payload.model_copy(update={"conversation_ticket_id":ticket_id}))


@router.post("/analyses/{analysis_id}/tickets/{ticket_id}/publication-preview")
def prepared_publication_preview(request, analysis_id: UUID, ticket_id: UUID, payload: PreviewIn):
    return publication_preview(request, analysis_id, None, payload.model_copy(update={"conversation_ticket_id":ticket_id}))


@router.post("/analyses/{analysis_id}/tickets/{ticket_id}/publications")
def create_prepared_publication(request, analysis_id: UUID, ticket_id: UUID, payload: PublicationIn):
    return create_publication(request, analysis_id, None, payload.model_copy(update={"conversation_ticket_id":ticket_id}))
