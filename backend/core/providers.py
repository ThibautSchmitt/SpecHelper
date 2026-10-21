"""Two terminal adapters, explicit availability, and a small shared queue policy."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import AIConnection, AISession, Job, Request

PROVIDERS = {"codex": 1, "claude": 2}


def connection_for(agent):
    return AIConnection.objects.get_or_create(pk=PROVIDERS[agent], defaults={"agent": agent})[0]


def ensure_connections():
    return [connection_for(agent) for agent in PROVIDERS]


def candidates(exclude=(), preferred=None):
    connections = AIConnection.objects.filter(enabled=True, status="CONNECTED").exclude(
        pk__in=exclude
    )
    connections = connections.filter(availability__in=["AVAILABLE", "UNKNOWN"])
    values = list(connections.order_by("id"))
    return sorted(values, key=lambda c: c.pk != preferred) if preferred else values


def public(connection):
    availability = connection.availability
    if connection.status != "CONNECTED" and availability not in {"QUOTA_EXHAUSTED", "ERROR"}:
        availability = "UNKNOWN"
    return {
        "id": connection.id,
        "agent": connection.agent,
        "account": connection.account,
        "status": connection.status,
        "availability": availability,
        "enabled": connection.enabled,
        "checked_at": connection.checked_at,
        "usage": "UNKNOWN",
        "reset": "UNKNOWN",
    }


def mark_failure(connection_id, kind, retry_seconds=None):
    # Only a typed runtime observation can mark a quota as exhausted. Retry times
    # are not presented as a provider's remaining quota or official reset time.
    retry = None
    if kind == "BUSY":
        retry = timezone.now() + timedelta(seconds=min(max(retry_seconds or 30, 1), 3600))
    AIConnection.objects.filter(pk=connection_id).update(
        availability=kind, retry_after=retry, checked_at=timezone.now()
    )


def release_connections(ids):
    AIConnection.objects.filter(pk__in=ids, availability="BUSY", retry_after__isnull=True).update(
        availability="AVAILABLE"
    )


def recover_orphaned_leases():
    active = {
        pk
        for payload in Job.objects.filter(kind="analysis", status="RUNNING").values_list(
            "payload", flat=True
        )
        for pk in payload.get("connection_ids", [])
    }
    AIConnection.objects.filter(availability="BUSY", retry_after__isnull=True).exclude(
        pk__in=active
    ).update(availability="AVAILABLE")


def refresh_unknown_connections(caller):
    now = timezone.now()
    AIConnection.objects.filter(availability="BUSY", retry_after__lte=now).update(
        availability="UNKNOWN", retry_after=None
    )
    for connection in AIConnection.objects.filter(enabled=True, availability="UNKNOWN"):
        if connection.checked_at and (now - connection.checked_at).total_seconds() < 30:
            continue
        try:
            value = caller("/health?agent=" + connection.agent)
        except ValueError:
            AIConnection.objects.filter(pk=connection.pk).update(checked_at=now)
            continue
        connected = value.get("status") == "CONNECTED"
        AIConnection.objects.filter(pk=connection.pk).update(
            status="CONNECTED" if connected else "DISCONNECTED",
            availability="AVAILABLE" if connected else "UNKNOWN",
            checked_at=now,
            account=value.get("account", ""),
        )


def bind_session(request, connection, role="primary"):
    session, _ = AISession.objects.get_or_create(
        request=request,
        role=role,
        agent=connection.agent,
        defaults={
            "connection": connection,
            "context_id": request.pk
            if role == "primary" and not request.ai_sessions.exists()
            else uuid.uuid4(),
        },
    )
    if session.connection_id != connection.pk:
        session.connection = connection
        session.save(update_fields=["connection"])
    if role == "primary":
        request.primary_session = session
        request.save(update_fields=["primary_session"])
    return session


@transaction.atomic
def reserve_for_job(job):
    """Called while claiming a queue row. No scheduler, priority or free agent loop."""
    request = Request.objects.select_for_update().get(pk=job.target)
    # Lock providers in a stable order so two workers cannot reserve the same capacity.
    list(AIConnection.objects.select_for_update().order_by("id"))
    choices = candidates(preferred=request.session.connection_id if request.session else None)
    if not choices:
        return False
    primary = choices[0]
    selected = [primary]
    if request.confrontation and len(choices) > 1:
        selected.append(choices[1])
    bind_session(request, primary)
    if request.confrontation:
        secondary = selected[-1]
        bind_session(request, secondary, "secondary")
        bind_session(request, primary, "synthesis")
    job.payload = {**job.payload, "connection_ids": [c.pk for c in selected]}
    job.save(update_fields=["payload"])
    AIConnection.objects.filter(pk__in=job.payload["connection_ids"]).update(
        availability="BUSY", retry_after=None
    )
    return True
