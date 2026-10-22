"""Human-confirmed delivery of immutable analysis versions to ticketing services."""

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import timedelta
from urllib.parse import unquote, urlsplit, urlunsplit

from django.db import IntegrityError, transaction
from django.utils import timezone
from ninja.errors import HttpError

from .i18n import translate
from .models import PublishedTicket
from .ticket_providers import NetworkUncertain, TicketProviderError, provider_for, render_body


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def validate_base_url(value):
    """Allow explicit self-hosted origins, but never URL credentials or ambiguous paths."""
    try:
        parsed = urlsplit(value.strip())
        parsed.port
    except ValueError:
        raise HttpError(422, "Invalid connector URL.") from None
    decoded = parsed.path
    for _ in range(4):
        decoded = unquote(decoded)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in decoded
        or any(segment in {".", ".."} for segment in decoded.split("/"))
        or any(ord(char) < 33 for char in value)
    ):
        raise HttpError(422, "Use an HTTP(S) connector URL without credentials, query or fragment.")
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def connector_dict(connector):
    return {
        "id": connector.pk,
        "environment_id": connector.environment_id,
        "name": connector.name,
        "platform": connector.platform,
        "base_url": connector.base_url,
        "username": connector.username,
        "api_version": connector.api_version,
        "projects": connector.projects,
        "default_project": connector.default_project,
        "status": connector.status,
        "error": connector.error,
        "has_secret": bool(connector.secret),
        "has_app_token": bool(connector.app_token),
    }


def publication_dict(value):
    return {
        **value.snapshot,
        "id": str(value.pk),
        "title": value.title,
        "body": value.body,
        "fields": value.fields,
        "snapshot": value.snapshot,
        "connector_id": value.connector_id,
        "connector_name": value.connector.name,
        "platform": value.platform,
        "project": value.project,
        "environment_name": value.version.environment_name,
        "request_id": str(value.request_id),
        "version_number": value.version.number,
        "external_id": value.external_id,
        "external_key": value.external_key,
        "external_reference": value.external_reference,
        "url": value.url,
        "status": value.observed_status,
        "error": value.error
        or (
            "Publication status is uncertain. Check the destination before retrying."
            if value.observed_status == PublishedTicket.Status.UNCERTAIN
            else ""
        ),
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "finished_at": value.finished_at,
        "idempotency_key": str(value.idempotency_key),
    }


NATIVE_FORM_ERRORS = {
    "GLPI template contains an unsupported field; use a supported template or the native ticket form",
    "GLPI template locks the ticket title or description; use the native ticket form",
    "GLPI template hides a field without an accessible default; use the native ticket form",
    "GLPI template contains unsupported multiple defaults",
    "GLPI template field metadata is unavailable",
    "GLPI template severity options are unavailable",
    "GLPI template default is not an accessible option",
    "GLPI profile cannot set the template priority",
    "Unsupported GLPI template field",
    "Unsupported GitHub issue form field",
    "Jira requires a field type not supported by this connector",
}
SAFE_PROVIDER_ERRORS = {
    "Ticket platform denied authentication or permission": "The ticket platform denied authentication or permission. Check the connector credentials and create-ticket permissions.",
    "Configure the GitHub connection": "Connect GitHub in Settings before publishing.",
    "Ticket options changed; review the publication again": "The destination options or template changed. Reload and review the publication options.",
    "Ticket template is no longer available": "The destination options or template changed. Reload and review the publication options.",
    "Ticket issue type is no longer available": "The destination options or template changed. Reload and review the publication options.",
    "Ticket selection is no longer available": "The destination options or template changed. Reload and review the publication options.",
    "GLPI template targets a different entity": "The selected template does not match this destination. Choose another template or project.",
    "GLPI connector supports the legacy v1 REST API only": "This connector supports GLPI REST API v1 only. Configure the legacy API URL.",
    "GLPI list is incomplete; narrow the destination": "The platform returned an incomplete destination list. Narrow the connector scope or use the platform's native ticket form.",
    "Complete all required ticket fields": "Complete all required ticket fields.",
    "A ticket field is fixed by the destination template": "A template-fixed field cannot be changed.",
    "Jira permits only one assignee": "Jira permits only one assignee.",
}


def safe_provider_error(exc):
    # Provider exceptions are intentionally reduced to a fixed message. Remote
    # response bodies and exception URLs can contain credentials or private data.
    if isinstance(exc, NetworkUncertain):
        return "Publication status is uncertain. Check the destination before retrying."
    if isinstance(exc, TicketProviderError):
        message = str(exc)
        if message in NATIVE_FORM_ERRORS:
            return "This destination requires fields or template rules that SpecHelper cannot apply safely. Choose another template or use the platform's native ticket form."
        if message in SAFE_PROVIDER_ERRORS:
            return SAFE_PROVIDER_ERRORS[message]
    return "The ticket platform refused the operation or could not be reached. Check the connector and permissions."


def accessible_projects(connector):
    try:
        return provider_for(connector).projects()
    except Exception as exc:
        raise HttpError(502, safe_provider_error(exc)) from None


def checked_access(connector, project):
    if project not in connector.projects:
        raise HttpError(403, "This project is not allowed for this connector.")
    try:
        provider = provider_for(connector)
        available = provider.projects()
        if project not in {str(item["id"]) for item in available}:
            raise HttpError(403, "This project is no longer accessible to the connector.")
    except HttpError:
        raise
    except Exception as exc:
        raise HttpError(502, safe_provider_error(exc)) from None
    return provider


def checked_options(connector, project, template_id="", issue_type=""):
    provider = checked_access(connector, project)
    try:
        options = provider.options(project, template_id=template_id, issue_type=issue_type)
    except Exception as exc:
        raise HttpError(502, safe_provider_error(exc)) from None
    if template_id and template_id not in {
        str(item["id"]) for item in options.get("templates", [])
    }:
        raise HttpError(422, "The selected ticket template is unavailable.")
    if issue_type and issue_type not in {
        str(item["id"]) for item in options.get("issue_types", [])
    }:
        raise HttpError(422, "The selected issue type is unavailable.")
    return provider, options


def normalized(value):
    return re.sub(
        r"[^a-z0-9]",
        "",
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower(),
    )


SECTION_NAMES = {
    "context": {"Context", "Background"},
    "need": {"Need", "Business need", "Problem"},
    "expected_behavior": {"Expected behavior", "Requested behavior"},
    "proposed_solution": {"Proposed solution", "Solution"},
    "technical_impact": {"Technical impact", "Technical impacts", "Impacts", "Technical analysis"},
    "risks": {"Risks", "Risks and considerations"},
    "acceptance_criteria": {"Acceptance criteria"},
}
SECTION_ALIASES = {
    key: {normalized(translate(label, language)) for label in labels for language in ("en", "fr")}
    for key, labels in SECTION_NAMES.items()
}
SECTION_ALIASES["risks"].add(normalized(translate("Risks and considerations", "fr").split()[0]))


def mapped_value(ticket, label):
    key = next((key for key, names in SECTION_ALIASES.items() if normalized(label) in names), "")
    value = ticket.get(key, "")
    if isinstance(value, list):
        return "\n".join("- " + str(item) for item in value)
    return str(value) if value is not None else ""


def preview(version, connector, project, template_id="", issue_type=""):
    require_environment(version, connector)
    if version.request.workflow != "request":
        raise HttpError(409, "A question cannot publish an external ticket.")
    if version.status not in {"READY", "PARTIAL"}:
        raise HttpError(409, "Only a completed result version can be published.")
    _, options = checked_options(connector, project, template_id, issue_type)
    artifact = version.artifacts.filter(name="ticket.md").first()
    body = artifact.content if artifact else ""
    template = options.get("template_body", "")
    if options.get("render_fields"):
        body = template
    if template:
        # Preserve the target's headings and defaults; replace only sections with
        # a known, deterministic counterpart in the immutable analysis ticket.
        parts = re.split(r"(?m)^(#{1,6})\s+([^\n]+)\n", template)
        for index in range(1, len(parts), 3):
            mapped = mapped_value(version.ticket, parts[index + 1])
            if mapped:
                parts[index + 2] = "\n" + mapped + "\n\n"
        body = parts[0] + "".join(
            f"{parts[index]} {parts[index + 1]}\n{parts[index + 2]}"
            for index in range(1, len(parts), 3)
        )
    values = {}
    for field in options.get("fields", []):
        field_id = str(field["id"])
        values[field_id] = field.get("default", "")
        mapped = mapped_value(version.ticket, field.get("name", field.get("label", field_id)))
        if (
            mapped
            and not field.get("read_only")
            and field.get("type", "text") in {"text", "textarea", "string"}
        ):
            values[field_id] = mapped
    return {
        **options,
        "title": str(options.get("defaults", {}).get("title") or version.ticket.get("title", "")),
        "body": body,
        "values": values,
    }


def validate_payload(payload, options):
    descriptors = {str(field["id"]): field for field in options.get("fields", [])}
    if set(payload["fields"]) - descriptors.keys():
        raise HttpError(422, "A field is not supported by this destination.")
    for field_id, field in descriptors.items():
        value = payload["fields"].get(field_id)
        if field.get("read_only") and value != field.get("default", ""):
            raise HttpError(422, "A template-fixed field cannot be changed.")
        if field.get("required") and (
            value is None or value == "" or value == [] or value is False
        ):
            raise HttpError(422, "Complete all required ticket fields.")
        if value not in (None, "", []):
            kind = field.get("type", "text")
            if kind not in {
                "text",
                "textarea",
                "string",
                "checkbox",
                "select",
                "multiselect",
                "number",
                "integer",
            }:
                raise HttpError(422, "This destination requires an unsupported field type.")
            if kind == "checkbox" and not isinstance(value, bool):
                raise HttpError(422, "Enter a valid checkbox value.")
            if kind == "multiselect" and not isinstance(value, list):
                raise HttpError(422, "Enter a valid multiple selection.")
            if kind in {"text", "textarea", "string"} and not isinstance(value, str):
                raise HttpError(422, "Enter a valid text field value.")
        choices = field.get("options", [])
        if value not in (None, "", []) and choices:
            allowed = {
                str(item.get("id", item.get("value", ""))) if isinstance(item, dict) else str(item)
                for item in choices
            }
            selected = value if isinstance(value, list) else [value]
            if any(str(item) not in allowed for item in selected):
                raise HttpError(422, "A selected field value is unavailable.")
    for key in ("labels", "assignees"):
        allowed = {
            str(item["id"]) if isinstance(item, dict) else str(item)
            for item in options.get(key, [])
        }
        if any(item not in allowed for item in payload[key]):
            raise HttpError(422, "A selected label or assignee is unavailable.")
    if not payload["title"].strip() or not render_body(payload, options).strip():
        raise HttpError(422, "Enter a ticket title and description.")


def store_success(record, result):
    url = str(result.get("url", ""))
    try:
        parsed = urlsplit(url)
        parsed.port
        origin = urlsplit(record.connector.base_url)
        allowed_origin = (
            "github.com"
            if record.platform == "github" and origin.hostname == "api.github.com"
            else origin.netloc.lower()
        )
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.scheme != origin.scheme
            or parsed.netloc.lower() != allowed_origin
            or parsed.username is not None
            or parsed.password is not None
            or any(ord(char) < 33 for char in url)
        ):
            raise ValueError
    except ValueError:
        # The remote write may have succeeded, but an unsafe URL is never shown.
        raise NetworkUncertain("The ticket platform returned an unsafe link") from None
    raw_id = result.get("external_id")
    if (
        isinstance(raw_id, bool)
        or not isinstance(raw_id, (str, int))
        or (isinstance(raw_id, int) and raw_id <= 0)
        or not str(raw_id).strip()
        or str(raw_id) != str(raw_id).strip()
        or len(str(raw_id)) > 255
    ):
        raise NetworkUncertain("The ticket platform did not return an identifier")
    external_id = str(raw_id)
    external_key = result.get("external_key")
    if external_key is None:
        external_key = ""
    if (
        isinstance(external_key, bool)
        or not isinstance(external_key, (str, int))
        or len(str(external_key)) > 255
    ):
        raise NetworkUncertain("The ticket platform did not return a valid ticket key")
    try:
        with transaction.atomic():
            PublishedTicket.objects.filter(pk=record.pk).update(
                external_id=external_id,
                external_key=str(external_key),
                url=url[:2000],
                status=PublishedTicket.Status.PUBLISHED,
                error="",
                updated_at=timezone.now(),
                finished_at=timezone.now(),
            )
    except IntegrityError:
        raise NetworkUncertain("The external identity needs reconciliation") from None


def require_environment(version, connector):
    """Keep new external writes within the request's configured environment."""
    if (
        not version.request.environment_id
        or connector.environment_id != version.request.environment_id
    ):
        raise HttpError(409, "Choose a ticket connector configured for this request's environment.")


def publish(version, connector, payload):
    if payload.get("confirmed") is not True:
        raise HttpError(422, "Explicit human confirmation is required to publish a ticket.")
    if version.request.workflow != "request":
        raise HttpError(409, "A question cannot publish an external ticket.")
    if version.status not in {"READY", "PARTIAL"}:
        raise HttpError(409, "Only a completed result version can be published.")
    project = payload["project"]
    destination = canonical_hash(
        {
            "platform": connector.platform,
            "base_url": connector.base_url.rstrip("/"),
            "project": project,
        }
    )
    snapshot = {
        key: payload[key]
        for key in (
            "title",
            "body",
            "fields",
            "labels",
            "assignees",
            "template_id",
            "issue_type",
            "options_revision",
        )
    }
    digest = canonical_hash(snapshot)
    key = payload["idempotency_key"]
    existing = PublishedTicket.objects.filter(idempotency_key=key).first()
    if existing and (
        existing.payload_hash != digest
        or existing.version_id != version.pk
        or existing.destination != destination
    ):
        raise HttpError(
            409,
            "This publication key was already used with different content or a different destination.",
        )
    active = (
        PublishedTicket.objects.filter(version=version, destination=destination)
        .exclude(status=PublishedTicket.Status.ERROR)
        .first()
    )
    if active is not None:
        # An old, definitively rejected attempt must never reactivate after a
        # later attempt has claimed or completed the same logical publication.
        existing = active
    if existing and existing.payload_hash != digest:
        raise HttpError(
            409,
            "This result already has a publication attempt for this destination. Review that attempt first.",
        )
    legacy_recovery = (
        existing is not None
        and existing.connector_id == connector.pk
        and existing.status
        in {
            PublishedTicket.Status.PUBLISHED,
            PublishedTicket.Status.PUBLISHING,
            PublishedTicket.Status.UNCERTAIN,
        }
    )
    if not legacy_recovery:
        require_environment(version, connector)
    if existing is not None:
        # Recovery always uses the original destination credential, including
        # historical shared connectors retained by the environment migration.
        connector = existing.connector
    if existing and existing.status == PublishedTicket.Status.PUBLISHED:
        return existing
    if (
        existing
        and existing.status == PublishedTicket.Status.PUBLISHING
        and existing.updated_at > timezone.now() - timedelta(seconds=90)
    ):
        return existing

    reconciling = existing is not None and existing.status in {
        PublishedTicket.Status.UNCERTAIN,
        PublishedTicket.Status.PUBLISHING,
    }
    if reconciling:
        # Reconciliation is a read of the original operation. A later template
        # change must not prevent recovery of an already accepted external ticket.
        provider = checked_access(connector, project)
    else:
        provider, options = checked_options(
            connector, project, payload["template_id"], payload["issue_type"]
        )
        if payload["options_revision"] != options.get("revision"):
            raise HttpError(
                409,
                "The destination options or template changed. Review the publication preview again.",
            )
        validate_payload(payload, options)
    if existing is None:
        try:
            with transaction.atomic():
                record = PublishedTicket.objects.create(
                    request=version.request,
                    version=version,
                    connector=connector,
                    platform=connector.platform,
                    project=project,
                    destination=destination,
                    idempotency_key=key,
                    external_reference="spechelper:" + str(uuid.uuid4()),
                    title=payload["title"],
                    body=payload["body"],
                    fields=payload["fields"],
                    snapshot=snapshot,
                    payload_hash=digest,
                )
        except IntegrityError:
            record = (
                PublishedTicket.objects.filter(version=version, destination=destination)
                .exclude(status=PublishedTicket.Status.ERROR)
                .first()
            )
            if record is None or record.payload_hash != digest:
                raise HttpError(
                    409, "A concurrent publication claimed this destination or publication key."
                ) from None
            return record
    else:
        record = existing
        try:
            with transaction.atomic():
                claimed = PublishedTicket.objects.filter(
                    pk=record.pk, status=record.status, updated_at=record.updated_at
                ).update(
                    status=PublishedTicket.Status.PUBLISHING,
                    updated_at=timezone.now(),
                    error="",
                    finished_at=None,
                )
        except IntegrityError:
            active = (
                PublishedTicket.objects.filter(version=version, destination=destination)
                .exclude(status=PublishedTicket.Status.ERROR)
                .first()
            )
            if active is not None and active.payload_hash == digest:
                return active
            raise HttpError(409, "A newer publication already claimed this destination.") from None
        if not claimed:
            record.refresh_from_db()
            return record
    try:
        if reconciling:
            found = provider.find(project, record.external_reference)
            if found is None:
                raise NetworkUncertain(
                    "The previous publication has not been found; no new ticket was created"
                )
            store_success(record, found)
        else:
            result = provider.create(project, snapshot, record.external_reference)
            store_success(record, result)
    except Exception as exc:
        # A crash/unexpected exception during a write may occur after acceptance.
        # Only the provider's explicit rejection is safe to retry as a new write.
        uncertain = (
            reconciling
            or isinstance(exc, NetworkUncertain)
            or not isinstance(exc, TicketProviderError)
        )
        PublishedTicket.objects.filter(pk=record.pk).update(
            status=PublishedTicket.Status.UNCERTAIN if uncertain else PublishedTicket.Status.ERROR,
            error=safe_provider_error(NetworkUncertain("") if uncertain else exc),
            updated_at=timezone.now(),
            finished_at=timezone.now(),
        )
    record.refresh_from_db()
    return record
