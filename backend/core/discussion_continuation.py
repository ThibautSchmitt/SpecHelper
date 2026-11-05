"""Explicit conversation transfers when the selected assistant cannot continue."""

import copy
import hashlib
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from .library_assistant import connection_snapshot
from .models import (
    AIConnection,
    AIIdentity,
    AISession,
    InstanceSettings,
    Job,
    Request,
    RequestMessage,
)
from .providers import candidates, public


def selected_session(value, job=None):
    state = value.discussion_state
    key = state.get("session_pk")
    if not key and job:
        key = job.payload.get("session_pk")
    if not key:
        reply = value.messages.filter(kind="discussion_reply").order_by("-id").first()
        key = reply.data.get("session_pk") if reply else None
    if not key:
        key = state.get("sessions", {}).get(state.get("owner"))
    return (
        AISession.objects.select_related("connection", "connection__identity")
        .filter(pk=key, request=value, role__startswith="d-")
        .first()
    )


def assistant(value, job=None):
    session = selected_session(value, job)
    if not session:
        return None
    connection = copy.copy(session.connection) if session.connection else None
    if connection:
        # Availability applies to the configuration actually selected for this
        # session, even if its settings have since changed.
        connection.model = session.model_snapshot
        connection.agent = session.agent
        connection.reasoning_effort = session.reasoning_effort_snapshot
        identity = AIIdentity.objects.filter(pk=session.identity_snapshot).first()
        if identity:
            connection.identity = identity
        observed = public(connection)
        availability = observed["availability"]
    else:
        observed = {"status":"DISCONNECTED", "enabled":False}
        availability = "DISCONNECTED"
    if not connection or not connection.enabled or connection.status != "CONNECTED" or observed["status"] != "CONNECTED":
        continuation_reason = "connection_unavailable"
    elif "analyst" not in connection.roles:
        continuation_reason = "analyst_role_removed"
    elif availability == "QUOTA_EXHAUSTED":
        continuation_reason = "quota_exhausted"
    else:
        continuation_reason = ""
    reply = (
        value.messages.filter(kind="discussion_reply", data__session_pk=session.pk)
        .order_by("-id")
        .first()
    )
    return {
        "connection_id": session.connection_id,
        "name": session.connection_name_snapshot
        or (connection.name if connection else session.agent),
        "agent": session.agent,
        "model": (reply.data.get("model") if reply else None) or session.model_snapshot,
        "reasoning_effort": session.reasoning_effort_snapshot,
        "availability": availability,
        "continuation_reason": continuation_reason,
        **{key:observed[key] for key in ("status", "enabled", "quota_windows", "quota_status", "availability_issue") if key in observed},
    }


def option(connection):
    snapshot = connection_snapshot(connection, "discussion")
    token = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return {
        "connection_id": connection.pk,
        "name": connection.name or connection.agent,
        "agent": connection.agent,
        "model": connection.model,
        "reasoning_effort": connection.reasoning_effort,
        "configuration_token": token,
    }


def history(value, job=None):
    """Recorded configurations in selection order, without private native contexts."""
    current = selected_session(value, job)
    reported = dict(value.messages.filter(kind="discussion_reply").order_by("id").values_list(
        "data__session_pk", "data__model"
    ))
    rows = []
    previous_key = None
    for session in value.ai_sessions.filter(role__startswith="d-").order_by("id"):
        model = reported.get(session.pk) or session.model_snapshot
        key = (session.connection_id, session.agent, model, session.reasoning_effort_snapshot, session.identity_snapshot)
        item = {"connection_id":session.connection_id, "name":session.connection_name_snapshot or session.agent,
                "agent":session.agent, "model":model, "reasoning_effort":session.reasoning_effort_snapshot,
                "current":bool(current and session.pk == current.pk), "used":bool(session.runtime_id)}
        if rows and key == previous_key:
            rows[-1] = {**item, "used":rows[-1]["used"] or item["used"], "current":rows[-1]["current"] or item["current"]}
        else:
            rows.append(item)
        previous_key = key
    return rows


def available_options(value):
    return [
        option(row)
        for row in candidates()
        if "analyst" in row.roles
        and row.pk != value.discussion_state.get("connection_id")
        and public(row)["availability"] == "AVAILABLE"
    ]


def options(value):
    source = assistant(value)
    allowed = bool(
        source
        and source["continuation_reason"]
        and value.discussion_state.get("mode", "discussion") == "discussion"
    )
    return {
        "revision": value.discussion_state.get("revision", 0),
        "can_continue": allowed,
        "options": available_options(value) if allowed else [],
    }


@transaction.atomic
def continue_with(analysis_id, payload, browser_actor):
    from .discussion import KIND, MessageIn, enqueue, idle
    from .i18n import translate

    # Match worker admission lock order: admission -> job -> conversation.
    # No running provider process is cancelled or transferred by this operation.
    InstanceSettings.objects.get_or_create(pk=1)
    InstanceSettings.objects.select_for_update().get(pk=1)
    job = (
        Job.objects.select_for_update()
        .filter(kind=KIND, target=str(analysis_id))
        .order_by("-id")
        .first()
    )
    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id)
    state = value.discussion_state
    if payload.expected_revision != state.get("revision", 0):
        raise HttpError(409, "The conversation changed. Refresh before sending.")
    source = assistant(value, job)
    if not state.get("enabled") or state.get("mode", "discussion") != "discussion" or not source:
        raise HttpError(409, "This conversation cannot change assistant at this stage.")
    if not source["continuation_reason"]:
        raise HttpError(
            409, "The current assistant can continue again. Refresh the conversation."
        )
    target = get_object_or_404(AIConnection.objects.select_for_update(), pk=payload.connection_id)
    choices = {item["connection_id"]: item for item in available_options(value)}
    if target.pk not in choices:
        raise HttpError(
            409, "The selected assistant is no longer available. Refresh the selection."
        )
    if choices[target.pk]["configuration_token"] != payload.configuration_token:
        raise HttpError(
            409, "The selected model or reasoning configuration changed. Refresh the selection."
        )
    pending = (
        job and job.status == "QUEUED" and job.payload.get("revision") == state.get("revision")
    )
    if job and (
        job.status == "RUNNING"
        or job.payload.get("connection_ids")
        or job.payload.get("awaiting_stop")
    ):
        raise HttpError(409, "Wait for the current response or cancel it first.")
    if pending:
        job.status, job.finished_at = "CANCELLED", timezone.now()
        job.save(update_fields=["status", "finished_at"])
    idle(value)
    # Retry the preserved pending/failed message. A completed conversation only
    # changes its session; it must not generate a duplicate answer on transfer.
    drafting = job and any(job.payload.get(key) for key in (
        "ticket_preparation", "analysis_preparation", "goal_generation"
    ))
    retry = bool(not drafting and (pending or (job and job.status == "ERROR")))
    if retry:
        value = enqueue(
            value.pk,
            MessageIn(
                expected_revision=payload.expected_revision,
                connection_id=target.pk,
                restart_session=True,
            ),
            browser_actor,
        )
    else:
        from .providers import identity_for

        session = AISession.objects.create(
            request=value,
            role="d-shared",
            connection=target,
            agent=target.agent,
            model_snapshot=target.model,
            reasoning_effort_snapshot=target.reasoning_effort,
            connection_name_snapshot=target.name,
            identity_snapshot=identity_for(target).pk,
        )
        state.update(
            session_pk=session.pk, connection_id=target.pk, revision=state.get("revision", 0) + 1
        )
        value.discussion_state = state
        value.save(update_fields=["discussion_state", "updated_at"])
    target_info = choices[target.pk]
    content = translate(
        "The conversation continues with {name}. A new session receives the recorded history and project context; previous answers remain unverified hypotheses.",
        value.language,
        name=target_info["name"],
    )
    data = {
        "previous_assistant": source,
        "assistant": {k: v for k, v in target_info.items() if k != "configuration_token"},
        "native_session_transferred": False,
    }
    if retry:
        # Replace enqueue's generic restart notice with one informative event.
        message = value.messages.filter(kind="session_notice").latest("id")
        message.content, message.data = content, data
        message.save(update_fields=["content", "data"])
    else:
        RequestMessage.objects.create(
            request=value, role="assistant", kind="session_notice", content=content, data=data
        )
    return value
