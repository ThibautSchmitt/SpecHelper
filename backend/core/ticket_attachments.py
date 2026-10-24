"""Explicit, bounded publication of selected immutable attachment bytes."""

import hashlib

from django.db import transaction
from django.utils import timezone
from ninja.errors import HttpError

from .file_validation import MAX_BYTES, attachment_path, inspect_file
from .models import PublishedTicket


def available_attachments(version, connector, policy=None):
    supported = connector.platform in {"gitlab", "jira", "glpi"}
    if policy is not None:
        supported = supported and policy.get("enabled", False)
    rows = []
    for attachment in version.request.attachments.order_by("name", "id"):
        row = {
            "id": str(attachment.pk),
            "name": attachment.name,
            "size": attachment.size,
            "mime": attachment.content_type,
            "kind": "original",
            "transferable": supported,
            "reason": ""
            if supported
            else "This connector cannot upload issue attachments through its supported API.",
        }
        try:
            if (
                any(ord(char) < 32 for char in attachment.name)
                or "/" in attachment.name
                or "\\" in attachment.name
            ):
                raise HttpError(422, "Invalid attachment name.")
            path = attachment_path(attachment)
            mime = inspect_file(path, attachment.name)
            if path.stat().st_size != attachment.size or mime != attachment.content_type:
                raise HttpError(422, "The attachment changed. Upload it again before publishing.")
            row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (HttpError, OSError):
            row.update(
                transferable=False,
                reason="The attachment is unavailable or no longer matches its validated metadata.",
            )
        rows.append(row)
    goal = version.artifacts.filter(name="goal.md").first()
    if goal:
        content = goal.content.encode()
        rows.append(
            {
                "id": "goal",
                "name": "goal.md",
                "size": len(content),
                "mime": "text/plain",
                "sha256": hashlib.sha256(content).hexdigest(),
                "kind": "goal",
                "transferable": supported and 0 < len(content) <= MAX_BYTES,
                "reason": ""
                if supported
                else "This connector cannot upload issue attachments through its supported API.",
            }
        )
    if policy:
        for row in rows:
            if row["size"] > policy.get("max_bytes", MAX_BYTES):
                row.update(
                    transferable=False,
                    reason="The attachment exceeds this destination's upload limit.",
                )
            elif not policy.get("enabled"):
                row.update(
                    transferable=False,
                    reason="Attachment upload is disabled or the connector's upload permission could not be verified.",
                )
    return rows


def selected_attachments(version, connector, payload, project="", policy=None):
    if not payload.get("include_attachments"):
        if payload.get("attachment_ids") or payload.get("include_goal"):
            raise HttpError(422, "Enable Include attachments before selecting files to transfer.")
        return []
    identifiers = [str(value) for value in payload.get("attachment_ids", [])]
    if payload.get("include_goal"):
        identifiers.append("goal")
    if len(identifiers) != len(set(identifiers)):
        raise HttpError(422, "Select each attachment only once.")
    if policy is None and project:
        policy = attachment_policy(connector, project)
    available = {row["id"]: row for row in available_attachments(version, connector, policy)}
    if any(
        identifier not in available or not available[identifier]["transferable"]
        for identifier in identifiers
    ):
        raise HttpError(422, "A selected attachment cannot be transferred to this destination.")
    rows = [available[identifier] for identifier in identifiers]
    if len(rows) > 20 or sum(row["size"] for row in rows) > 50 * 1024 * 1024:
        raise HttpError(422, "Select at most 20 attachments and 50 MB per publication.")
    return rows


def attachment_policy(connector, project):
    from .ticket_providers import provider_for

    try:
        policy = provider_for(connector).attachment_policy(project)
        return policy if isinstance(policy, dict) else None
    except Exception:
        return {"enabled": False, "max_bytes": 0}


def selected_bytes(record, row):
    if row["kind"] == "goal":
        artifact = record.version.artifacts.get(name="goal.md")
        content = artifact.content.encode()
    else:
        attachment = record.request.attachments.get(pk=row["id"])
        path = attachment_path(attachment)
        if inspect_file(path, attachment.name) != row["mime"]:
            raise HttpError(422, "The selected attachment changed.")
        content = path.read_bytes()
    if len(content) != row["size"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
        raise HttpError(422, "The selected attachment changed.")
    return content


def deliver_attachments(record, provider):
    """Claim each transfer before writing; uncertain transfers are never blindly repeated."""
    for row in record.snapshot.get("selected_attachments", []):
        with transaction.atomic():
            current = PublishedTicket.objects.select_for_update().get(pk=record.pk)
            delivery = current.attachment_delivery
            if any(item["id"] == row["id"] for item in delivery):
                continue
            item = {"id": row["id"], "name": row["name"], "status": "TRANSFERRING"}
            delivery.append(item)
            PublishedTicket.objects.filter(pk=record.pk).update(
                attachment_delivery=delivery, updated_at=timezone.now()
            )
        try:
            content = selected_bytes(record, row)
            result = provider.attach(
                record.project, record.external_key or record.external_id, row, content
            )
            item.update(status="TRANSFERRED", external_id=str(result.get("id", "")))
        except Exception:
            # The issue already exists. A file may have reached the destination;
            # retain that distinction and never create another issue as a retry.
            item.update(
                status="UNCERTAIN",
                error="The issue exists, but this attachment transfer could not be confirmed. Check the destination before any manual retry.",
            )
        with transaction.atomic():
            current = PublishedTicket.objects.select_for_update().get(pk=record.pk)
            delivery = [
                item if previous["id"] == row["id"] else previous
                for previous in current.attachment_delivery
            ]
            PublishedTicket.objects.filter(pk=record.pk).update(
                attachment_delivery=delivery, updated_at=timezone.now()
            )
    record.refresh_from_db()
