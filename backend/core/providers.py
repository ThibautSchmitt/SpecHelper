"""Identity-aware terminal configurations and shared capacity leases."""

import math
import uuid
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import AIConnection, AIIdentity, AISession, Job, Request

PROVIDERS = {"codex": 1, "claude": 2}


def identity_for(connection):
    if connection.identity_id:
        identity = AIIdentity.objects.get(pk=connection.identity_id)
        connection.identity = identity
        # Older integrations update the original configuration row directly.
        if (
            identity.credential_id is None
            and identity.status in {"UNKNOWN", "DISCONNECTED"}
            and connection.status == "CONNECTED"
            and identity.availability == "UNKNOWN"
        ):
            identity.status, identity.availability = connection.status, connection.availability
            identity.save(update_fields=["status", "availability"])
        return identity
    identity = AIIdentity.objects.filter(agent=connection.agent, credential_id=None).first()
    if identity is None:
        identity = AIIdentity.objects.create(
            agent=connection.agent,
            account=connection.account,
            status=connection.status,
            availability=connection.availability,
            retry_after=connection.retry_after,
            checked_at=connection.checked_at,
        )
    connection.identity = identity
    connection.save(update_fields=["identity"])
    return identity


def connection_for(agent):
    value = AIConnection.objects.filter(agent=agent).order_by("id").first()
    if value is None:
        legacy_id = PROVIDERS[agent]
        values = {"pk": legacy_id} if not AIConnection.objects.filter(pk=legacy_id).exists() else {}
        value = AIConnection.objects.create(
            **values, agent=agent, name="ChatGPT / Codex" if agent == "codex" else "Claude"
        )
    identity_for(value)
    return value


def ensure_connections():
    # Bootstrap legacy installations only; deleted user configurations stay deleted.
    if not AIConnection.objects.exists() and not AIIdentity.objects.exists():
        return [connection_for(agent) for agent in PROVIDERS]
    return list(AIConnection.objects.select_related("identity").order_by("id"))


def quota_exhausted(identity):
    now = timezone.now()
    for window in normalize_quota_windows(identity.quota_windows).values():
        if not isinstance(window, dict) or window.get("exhausted") is not True:
            continue
        reset = window.get("resets_at")
        try:
            reset = datetime.fromisoformat(reset.replace("Z", "+00:00")) if reset else None
        except (ValueError, TypeError):
            reset = None
        if reset is None or timezone.is_naive(reset) or reset > now:
            return True
    return False


def normalize_quota_windows(value):
    """Keep only observed, finite session/weekly fields with aware reset times."""
    windows = {}
    if not isinstance(value, dict):
        return windows
    for name in ("session", "weekly"):
        item = value.get(name)
        if not isinstance(item, dict):
            continue
        window = {}
        used = item.get("used_percent")
        if (
            isinstance(used, (int, float))
            and not isinstance(used, bool)
            and math.isfinite(used)
            and 0 <= used <= 100
        ):
            window["used_percent"] = used
            window["exhausted"] = used >= 100
        if isinstance(item.get("exhausted"), bool):
            window["exhausted"] = item["exhausted"] or window.get("exhausted", False)
        for timestamp_name in ("resets_at", "observed_at"):
            reset = item.get(timestamp_name)
            if isinstance(reset, str):
                try:
                    parsed = datetime.fromisoformat(reset.replace("Z", "+00:00"))
                    if not timezone.is_naive(parsed):
                        window[timestamp_name] = parsed.isoformat()
                except ValueError:
                    pass
        if "used_percent" in window or "exhausted" in window:
            windows[name] = window
    return windows


def record_quota(connection, windows):
    observed = normalize_quota_windows(windows)
    if not observed:
        return
    identity = identity_for(connection)
    now = timezone.now().isoformat()
    observed = {name: {**window, "observed_at": now} for name, window in observed.items()}
    merged = {**group_windows(list(quota_group(identity))), **observed}
    metadata = (
        identity.quota_windows.get("_status") if isinstance(identity.quota_windows, dict) else None
    )
    identity.quota_windows = merged
    changes = {
        "quota_windows": {**merged, **({"_status": metadata} if metadata else {})},
        "checked_at": timezone.now(),
    }
    if quota_exhausted(identity):
        changes["availability"] = "QUOTA_EXHAUSTED"
    identities = list(quota_group(identity).values_list("pk", flat=True))
    AIIdentity.objects.filter(pk__in=identities).update(**changes)
    if "availability" in changes:
        AIConnection.objects.filter(identity_id__in=identities).exclude(
            availability="MODEL_UNAVAILABLE"
        ).update(availability=changes["availability"])


def quota_group(identity):
    return (
        AIIdentity.objects.filter(agent=identity.agent, account_key=identity.account_key)
        if identity.account_key
        else AIIdentity.objects.filter(pk=identity.pk)
    )


def group_windows(identities):
    windows = {}
    for identity in identities:
        for name, value in normalize_quota_windows(identity.quota_windows).items():
            previous = windows.get(name)
            if (
                previous is None
                or value.get("observed_at", "") > previous.get("observed_at", "")
                or (
                    not value.get("observed_at")
                    and not previous.get("observed_at")
                    and value.get("exhausted")
                )
            ):
                windows[name] = value
    return windows


def group_unavailable(identity):
    return any(
        item.availability not in {"AVAILABLE", "UNKNOWN"} or quota_exhausted(item)
        for item in quota_group(identity)
    )


def candidates(exclude=(), preferred=None):
    values = []
    for connection in (
        AIConnection.objects.filter(enabled=True).exclude(pk__in=exclude).select_related("identity")
    ):
        if connection.model:
            from .models import AIModel

            if AIModel.objects.filter(
                agent=connection.agent, identifier=connection.model, enabled=False
            ).exists():
                continue
        identity = identity_for(connection)
        if connection.status != "CONNECTED" or identity.status != "CONNECTED":
            continue
        if connection.availability not in {"AVAILABLE", "UNKNOWN"} or identity.availability not in {
            "AVAILABLE",
            "UNKNOWN",
        }:
            continue
        if not group_unavailable(identity):
            values.append(connection)
    return sorted(
        values,
        key=lambda c: (c.pk != preferred if preferred else not c.is_default, c.preference, c.pk),
    )


def public(connection):
    identity = identity_for(connection)
    availability = identity.availability
    if connection.availability not in {"AVAILABLE", "UNKNOWN"}:
        availability = connection.availability
    if quota_exhausted(identity):
        availability = "QUOTA_EXHAUSTED"
    group = list(quota_group(identity))
    exhausted = next(
        (item for item in group if item.availability == "QUOTA_EXHAUSTED" or quota_exhausted(item)),
        None,
    )
    if exhausted:
        availability = "QUOTA_EXHAUSTED"
    if connection.model:
        from .models import AIModel

        if AIModel.objects.filter(
            agent=connection.agent, identifier=connection.model, enabled=False
        ).exists():
            availability = "MODEL_UNAVAILABLE"
    return {
        "id": connection.id,
        "roles": connection.roles,
        "additional_instructions": connection.additional_instructions,
        "skill_overrides": connection.skill_overrides,
        "name": connection.name or connection.agent,
        "agent": connection.agent,
        "model": connection.model,
        "preference": connection.preference,
        "is_default": connection.is_default,
        "identity_id": str(identity.pk),
        "quota_identity_id": str(min(group, key=lambda item: str(item.pk)).pk),
        "account": identity.account,
        "status": identity.status,
        "availability": availability,
        "enabled": connection.enabled,
        "checked_at": identity.checked_at,
        "quota_windows": group_windows(group),
        "quota_status": identity.quota_windows.get("_status", {})
        if isinstance(identity.quota_windows, dict)
        else {},
        "usage": "UNKNOWN",
        "reset": "UNKNOWN",
    }


def observe(connection, value):
    identity = identity_for(connection)
    connected = value.get("status") == "CONNECTED"
    changes = {
        "status": "CONNECTED" if connected else "DISCONNECTED",
        "checked_at": timezone.now(),
        "account": str(value.get("account", ""))[:200],
    }
    key = value.get("account_key")
    if isinstance(key, str) and len(key) == 64 and all(char in "0123456789abcdef" for char in key):
        changes["account_key"] = key
    # Authentication health does not establish that an exhausted quota recovered.
    if identity.availability != "QUOTA_EXHAUSTED" and not quota_exhausted(identity):
        changes["availability"] = "AVAILABLE" if connected else "UNKNOWN"
    AIIdentity.objects.filter(pk=identity.pk).update(**changes)
    mirror_changes = {key: value for key, value in changes.items() if key != "account_key"}
    AIConnection.objects.filter(identity=identity).exclude(availability="MODEL_UNAVAILABLE").update(
        **mirror_changes
    )
    AIConnection.objects.filter(identity=identity, availability="MODEL_UNAVAILABLE").update(
        **{key: value for key, value in mirror_changes.items() if key != "availability"}
    )
    connection.refresh_from_db()
    if value.get("quota_windows"):
        record_quota(connection, value["quota_windows"])
    metadata = value.get("quota_status")
    if isinstance(metadata, dict) and metadata.get("state") in {
        "available",
        "unavailable",
        "error",
    }:
        # Persist only fixed public diagnostics; provider error bodies may contain secrets.
        safe = {
            "state": metadata["state"],
            "source": "codex_app_server" if connection.agent == "codex" else "claude_cli",
            "checked_at": timezone.now().isoformat(),
            "reason": metadata.get("reason")
            if metadata.get("reason")
            in {"not_connected", "unsupported_cli", "not_reported", "refresh_failed", ""}
            else "refresh_failed",
        }
        for member in quota_group(identity_for(connection)):
            windows = {**member.quota_windows, "_status": safe}
            AIIdentity.objects.filter(pk=member.pk).update(quota_windows=windows)
        # Only explicit backend permission establishes recovery; low percentages alone do not.
        if (
            connected
            and metadata["state"] == "available"
            and value.get("ordinary_usage_allowed") is True
        ):
            ids = list(quota_group(identity_for(connection)).values_list("pk", flat=True))
            AIIdentity.objects.filter(pk__in=ids, availability="QUOTA_EXHAUSTED").update(
                availability="AVAILABLE"
            )
            AIConnection.objects.filter(identity_id__in=ids, availability="QUOTA_EXHAUSTED").update(
                availability="AVAILABLE"
            )
        connection.refresh_from_db()
    return public(connection)


def runtime_identity(connection):
    identity = identity_for(connection)
    return str(identity.credential_id) if identity.credential_id else None


def mark_failure(connection_id, kind, retry_seconds=None, quota_windows=None):
    connection = AIConnection.objects.get(pk=connection_id)
    identity = identity_for(connection)
    retry = (
        timezone.now() + timedelta(seconds=min(max(retry_seconds or 30, 1), 3600))
        if kind == "BUSY"
        else None
    )
    changes = {"availability": kind, "retry_after": retry, "checked_at": timezone.now()}
    if kind == "AUTH_ERROR":
        changes["status"] = "DISCONNECTED"
    if kind == "QUOTA_EXHAUSTED":
        changes["quota_windows"] = {
            **identity.quota_windows,
            **normalize_quota_windows(quota_windows),
        }
    group = (
        quota_group(identity)
        if kind in {"QUOTA_EXHAUSTED", "BUSY"}
        else AIIdentity.objects.filter(pk=identity.pk)
    )
    ids = list(group.values_list("pk", flat=True))
    AIIdentity.objects.filter(pk__in=ids).update(**changes)
    AIConnection.objects.filter(identity_id__in=ids).exclude(
        availability="MODEL_UNAVAILABLE"
    ).update(**{key: value for key, value in changes.items() if key != "quota_windows"})


def release_connections(ids):
    identities = [
        pk
        for connection in AIConnection.objects.filter(pk__in=ids)
        for pk in quota_group(identity_for(connection)).values_list("pk", flat=True)
    ]
    AIIdentity.objects.filter(
        pk__in=identities, availability="BUSY", retry_after__isnull=True
    ).update(availability="AVAILABLE")
    AIConnection.objects.filter(
        identity_id__in=identities, availability="BUSY", retry_after__isnull=True
    ).update(availability="AVAILABLE")


def recover_orphaned_leases():
    active = {
        pk
        for payload in Job.objects.filter(
            kind__in=["analysis", "library_assistant"], status__in=["RUNNING", "CANCELLED"]
        ).values_list("payload", flat=True)
        for pk in payload.get("connection_ids", [])
    }
    active_identity_ids = {
        identity_id
        for connection in AIConnection.objects.filter(pk__in=active)
        for identity_id in quota_group(identity_for(connection)).values_list("pk", flat=True)
    }
    AIIdentity.objects.filter(availability="BUSY", retry_after__isnull=True).exclude(
        pk__in=active_identity_ids
    ).update(availability="AVAILABLE")
    AIConnection.objects.filter(availability="BUSY", retry_after__isnull=True).exclude(
        identity_id__in=active_identity_ids
    ).update(availability="AVAILABLE")


def refresh_unknown_connections(caller):
    now = timezone.now()
    for identity in AIIdentity.objects.all():
        if identity.availability == "BUSY" and identity.retry_after and identity.retry_after <= now:
            AIIdentity.objects.filter(pk=identity.pk).update(
                availability="UNKNOWN", retry_after=None
            )
            AIConnection.objects.filter(identity=identity).exclude(
                availability="MODEL_UNAVAILABLE"
            ).update(availability="UNKNOWN", retry_after=None)
            identity.availability = "UNKNOWN"
        if (
            identity.availability == "QUOTA_EXHAUSTED"
            and identity.quota_windows
            and not quota_exhausted(identity)
        ):
            AIIdentity.objects.filter(pk=identity.pk).update(
                availability="UNKNOWN", quota_windows={}
            )
            AIConnection.objects.filter(identity=identity).exclude(
                availability="MODEL_UNAVAILABLE"
            ).update(availability="UNKNOWN")
            identity.availability = "UNKNOWN"
        if identity.availability != "UNKNOWN" or (
            identity.checked_at and (now - identity.checked_at).total_seconds() < 30
        ):
            continue
        connection = AIConnection.objects.filter(identity=identity, enabled=True).first()
        if connection is None:
            continue
        try:
            suffix = "&identity_id=" + str(identity.credential_id) if identity.credential_id else ""
            observe(connection, caller("/health?agent=" + identity.agent + suffix))
        except ValueError:
            AIIdentity.objects.filter(pk=identity.pk).update(checked_at=now)


def bind_session(request, connection, role="primary"):
    identity = identity_for(connection)
    session = (
        AISession.objects.filter(
            request=request,
            role=role,
            connection=connection,
            agent=connection.agent,
            model_snapshot=connection.model,
            identity_snapshot=identity.pk,
        )
        .order_by("-id")
        .first()
    )
    if session is None:
        session = AISession.objects.create(
            request=request,
            role=role,
            connection=connection,
            agent=connection.agent,
            model_snapshot=connection.model,
            connection_name_snapshot=connection.name or connection.agent,
            identity_snapshot=identity.pk,
            context_id=request.pk
            if role == "primary" and not request.ai_sessions.exists()
            else uuid.uuid4(),
        )
    if role == "primary":
        request.primary_session = session
        request.save(update_fields=["primary_session"])
    return session


@transaction.atomic
def reserve_for_job(job, exclude=()):
    if job.kind == "library_assistant":
        from .library_assistant import reserve_job

        return reserve_job(job)
    request = Request.objects.select_for_update().get(pk=job.target)
    if request.confrontation:
        # The next public role is selected by the engine at its actual start,
        # rather than reserving N connections for the entire request.
        from .models import AISession, AnalysisRun
        from .orchestration import RoleUnavailable, select_connection
        from .orchestration_settings import get_config

        run = AnalysisRun.objects.filter(job=job).first()
        state = run.orchestration if run else {}
        config = state.get("config") or get_config(request.analysis_protocol)
        if (
            state.get("deadline_at")
            and datetime.fromisoformat(state["deadline_at"]) <= timezone.now()
        ):
            return True
        role = state.get("waiting_role") or state.get("current_role") or "analyst"
        order = ("analyst", "counter_analyst", "verifier")
        prior = [
            AISession.objects.get(pk=state["sessions"][r])
            for r in order[: order.index(role)]
            if r in state.get("sessions", {})
        ]
        try:
            select_connection(
                role,
                config,
                prior[-1].family_snapshot if prior else None,
                [s.family_snapshot for s in prior],
                exclude,
            )
        except RoleUnavailable as wait:
            job.payload = {**job.payload, "waiting_reason": wait.reason, "current_role": role}
            job.save(update_fields=["payload"])
            return False
        return True
    list(AIIdentity.objects.select_for_update().order_by("id"))
    list(AIConnection.objects.select_for_update().order_by("id"))
    choices = candidates(
        exclude=exclude, preferred=request.session.connection_id if request.session else None
    )
    if not choices:
        return False
    choices = [c for c in choices if "analyst" in c.roles]
    if not choices:
        return False
    primary = choices[0]
    selected = [primary]
    if request.confrontation:
        group_ids = set(quota_group(identity_for(primary)).values_list("pk", flat=True))
        secondary = next((c for c in choices[1:] if c.identity_id not in group_ids), primary)
        if secondary.pk != primary.pk:
            selected.append(secondary)
        bind_session(request, secondary, "secondary")
        bind_session(request, primary, "synthesis")
    bind_session(request, primary)
    job.payload = {
        **job.payload,
        "connection_ids": [c.pk for c in selected],
        "assignments": [
            {
                "connection_id": c.pk,
                "connection_name": c.name or c.agent,
                "agent": c.agent,
                "model": c.model or "runtime-default",
            }
            for c in selected
        ],
    }
    job.save(update_fields=["payload"])
    identity_ids = [
        pk for c in selected for pk in quota_group(identity_for(c)).values_list("pk", flat=True)
    ]
    AIIdentity.objects.filter(pk__in=identity_ids).update(availability="BUSY", retry_after=None)
    AIConnection.objects.filter(identity_id__in=identity_ids).exclude(
        availability="MODEL_UNAVAILABLE"
    ).update(availability="BUSY", retry_after=None)
    return True
