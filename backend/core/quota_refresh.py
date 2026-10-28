"""Persist post-invocation metadata without releasing or changing a capacity lease."""

from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import AIConnection, AIIdentity
from .providers import identity_for, quota_group, record_quota


@transaction.atomic
def record_invocation_metadata(payload, result):
    if not isinstance(result.get("quota_status"), dict):
        return
    identity_id = payload.get("identity_id")
    if identity_id is not None:
        try:
            identity_id = UUID(str(identity_id))
        except (ValueError, TypeError):
            return
    connection = AIConnection.objects.filter(agent=payload.get("agent", "codex"), identity__credential_id=identity_id).select_related("identity").first()
    if connection is None:
        return
    identity = identity_for(connection)
    group = quota_group(identity) if identity_id is not None else AIIdentity.objects.filter(agent=connection.agent, credential_id=None)
    members = list(group.order_by("pk"))
    list(AIIdentity.objects.select_for_update().filter(pk__in=[m.pk for m in members]).order_by("pk"))
    record_quota(connection, result.get("quota_windows", {}))
    metadata = result["quota_status"]
    state = metadata.get("state")
    if state not in {"available", "unavailable", "error"}:
        return
    safe = {"state": state, "source": "codex_app_server" if connection.agent == "codex" else f"{connection.agent}_cli", "checked_at": timezone.now().isoformat(),
            "reason": "" if state == "available" else "not_reported" if state == "unavailable" else "refresh_failed"}
    for member in AIIdentity.objects.filter(pk__in=[m.pk for m in members]):
        AIIdentity.objects.filter(pk=member.pk).update(quota_windows={**member.quota_windows, "_status": safe})
