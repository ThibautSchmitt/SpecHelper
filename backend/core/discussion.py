"""Single-assistant turns in the ordinary queue, separate from verified analysis cycles."""

import copy
import json
import uuid

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import BaseModel, ConfigDict, Field

from .agent import RULES, ProviderUnavailable, output_language_instruction, runtime_call
from .discussion_access import actor
from .models import AIConnection, AISession, Job, Request, RequestMessage
from .sensitive_data import configured_secrets, redact

router = Router(tags=["Conversation"])
KIND = "discussion"
BUSY = {"QUEUED", "RUNNING"}


class MessageIn(Schema):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="", max_length=30000)
    expected_revision: int = Field(ge=0)
    connection_id: int | None = Field(default=None, gt=0)
    restart_session: bool = False


class DeepIn(Schema):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    intent: str = Field(default="auto", pattern=r"^(auto|change)$")


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=12000)


def describe(value):
    state = value.discussion_state
    if not state.get("enabled"):
        return None
    job = Job.objects.filter(kind=KIND, target=str(value.pk)).order_by("-id").first()
    revision = state.get("revision", 0)
    return {
        "enabled": True,
        "mode": state.get("mode", "discussion"),
        "revision": revision,
        "has_new_messages": revision > state.get("analyzed_revision", -1),
        "connection_id": state.get("connection_id"),
        "job": {
            "id": job.pk,
            "status": job.status,
            "created_at": job.created_at,
            "error": job.error,
            "waiting_reason": job.payload.get("waiting_reason", ""),
        }
        if job and job.payload.get("revision") == revision
        else None,
    }


def idle(value):
    if Job.objects.filter(
        target=str(value.pk), kind__in=["analysis", KIND], status__in=BUSY
    ).exists():
        raise HttpError(409, "Wait for the current response or cancel it first.")
    if (
        Job.objects.filter(target=str(value.pk), kind__in=["analysis", KIND], status="CANCELLED")
        .exclude(payload__connection_ids=[])
        .exists()
    ):
        raise HttpError(409, "Wait for the cancelled assistant to stop.")
    if value.status == "NEEDS_CLARIFICATION":
        raise HttpError(409, "Answer the pending clarification before continuing.")


def pin_environment(value):
    """Use the existing frozen repository/context machinery for a read-only turn."""
    import re

    from .environment_context import freeze_context
    from .git_sources import repository_snapshot

    environment = value.environment
    if environment is None or environment.status != "READY":
        raise HttpError(409, "The environment must be synchronized")
    repos = list(environment.repositories.all())
    if not repos or any(not re.fullmatch(r"[a-f0-9]{40}", r.sha) for r in repos):
        raise HttpError(409, "The environment baseline is incomplete")
    value.baseline = [repository_snapshot(r) for r in repos]
    value.database_snapshot = (
        {"id": environment.database_id, "name": environment.database.name}
        if environment.database_id
        else {}
    )
    value.environment_name_snapshot = environment.name
    value.save(update_fields=["baseline", "database_snapshot", "environment_name_snapshot"])
    return freeze_context(value)


@transaction.atomic
def enqueue(value_id, payload, browser_actor, *, initial=False):
    from .library_assistant import connection_snapshot, safe_text
    from .providers import bind_session, candidates

    if not browser_actor:
        raise HttpError(409, "Reopen the conversation before editing the need.")
    value = (
        Request.objects.select_for_update(of=("self",))
        .select_related("environment__database")
        .get(pk=value_id)
    )
    idle(value)
    if initial:
        from .scope_service import assess

        if not assess(value):
            return value
    state = copy.deepcopy(value.discussion_state)
    if payload.expected_revision != state.get("revision", 0):
        raise HttpError(409, "The conversation changed. Refresh before sending.")
    retry = not initial and payload.restart_session and not payload.message.strip()
    if retry:
        previous_message = value.messages.filter(role="user").order_by("-id").first()
        if previous_message is None:
            raise HttpError(409, "There is no message to retry.")
        text = previous_message.content
    elif not initial:
        text = safe_text(payload.message)
    else:
        text = safe_text(value.need)
    owner_sessions = state.setdefault("sessions", {})
    previous = AISession.objects.filter(pk=owner_sessions.get(browser_actor), request=value).first()
    connection_id = payload.connection_id or (
        previous.connection_id if previous else state.get("connection_id")
    )
    if connection_id:
        connection = get_object_or_404(AIConnection, pk=connection_id, enabled=True)
    else:
        available = [c for c in candidates() if "analyst" in c.roles]
        connection = (
            available[0]
            if available
            else next(
                (
                    c
                    for c in AIConnection.objects.filter(enabled=True, status="CONNECTED").order_by(
                        "preference", "pk"
                    )
                    if "analyst" in c.roles
                ),
                None,
            )
        )
        if connection is None:
            raise HttpError(
                409, "Connect an assistant with the analyst role before starting a discussion."
            )
    if "analyst" not in connection.roles:
        raise HttpError(409, "Choose an AI connection allowed to act as analyst.")
    if not state.get("snapshot"):
        latest = value.versions.order_by("-number").first()
        state["snapshot"] = (
            copy.deepcopy(latest.context_snapshot)
            if latest and latest.context_snapshot
            else pin_environment(value)
        )
    from .providers import identity_for

    changed = previous and (
        previous.connection_id != connection.pk
        or previous.agent != connection.agent
        or previous.model_snapshot != connection.model
        or previous.reasoning_effort_snapshot != connection.reasoning_effort
        or previous.identity_snapshot != identity_for(connection).pk
    )
    if changed and not (payload.connection_id or payload.restart_session):
        raise HttpError(
            409, "The selected AI configuration changed. Start a new discussion session explicitly."
        )
    if payload.restart_session or changed:
        previous = None
    if payload.restart_session or changed:
        session = AISession.objects.create(
            request=value,
            role="d-" + browser_actor[:16],
            connection=connection,
            agent=connection.agent,
            model_snapshot=connection.model,
            reasoning_effort_snapshot=connection.reasoning_effort,
            connection_name_snapshot=connection.name,
            identity_snapshot=identity_for(connection).pk,
        )
    else:
        session = previous or bind_session(value, connection, "d-" + browser_actor[:16])
    owner_sessions[browser_actor] = session.pk
    if not initial and not retry:
        RequestMessage.objects.create(
            request=value,
            role="user",
            kind="discussion",
            content=text,
            data={"actor": browser_actor},
        )
    revision = state.get("revision", 0) + 1
    if changed or payload.restart_session:
        notice(value, "A new discussion session was started with the selected AI configuration.")
    state.update(enabled=True, mode="discussion", revision=revision, connection_id=connection.pk)
    value.discussion_state, value.status, value.error = state, "QUEUED", ""
    value.save(update_fields=["discussion_state", "status", "error", "updated_at"])
    assignment = connection_snapshot(connection, "discussion")
    assignment["public_role"] = "discussion"
    Job.objects.create(
        kind=KIND,
        target=str(value.pk),
        payload={
            "revision": revision,
            "session_pk": session.pk,
            "attempt_id": str(uuid.uuid4()),
            "message_id": value.messages.filter(role="user").latest("id").pk,
            "assignment": assignment,
            "snapshot": state["snapshot"],
            "connection_ids": [],
            "waiting_reason": "",
            "current_role": "analyst",
        },
    )
    return value


def notice(value, text):
    from .i18n import translate

    RequestMessage.objects.create(
        request=value,
        role="assistant",
        kind="session_notice",
        content=translate(text, value.language),
    )


def reserve(job):
    from .library_assistant import reserve_job

    reserved = reserve_job(job)
    if not reserved and "changed" in job.payload.get("waiting_reason", ""):
        job.payload["waiting_reason"] = (
            "The selected AI configuration changed. Cancel the pending turn, then resume with a new session."
        )
        job.save(update_fields=["payload"])
    return reserved


def recovery_messages(value, until):
    """Only recovery sends history; ordinary native continuations send the new turn."""
    messages = list(
        value.messages.filter(id__lte=until).exclude(kind="error").values("role", "kind", "content")
    )
    retained, size = [], 0
    for message in reversed(messages):
        if size + len(message["content"]) > 100000:
            break
        retained.append(message)
        size += len(message["content"])
    return {
        "initial_need": value.need,
        "messages": list(reversed(retained)),
        "older_messages_omitted": len(messages) - len(retained),
        "assistant_messages_are_unverified": True,
    }


def live(job):
    return Job.objects.filter(
        pk=job.pk, status="RUNNING", payload__attempt_id=job.payload["attempt_id"]
    ).exists()


def run_job(job, caller=None):
    """Native history remains in a private context; no analysis run or result is created."""
    from .environment_context import materialize_context
    from .git import request_workspace
    from .global_skills import catalog, registry_instructions
    from .models import DatabaseConnection
    from .postgres import parameters

    caller = caller or runtime_call
    with transaction.atomic():
        locked_job = Job.objects.select_for_update().get(pk=job.pk)
        if locked_job.status != "RUNNING":
            return
        Request.objects.filter(pk=job.target, status="QUEUED").update(
            status="CONTINUING_CONVERSATION"
        )
    value = Request.objects.get(pk=job.target)
    session = AISession.objects.select_related("connection").get(
        pk=job.payload["session_pk"], request=value
    )
    frozen = job.payload["snapshot"]
    scoped = copy.copy(value)
    scoped.baseline = frozen["dossier"]["baseline"]
    workspace = request_workspace(scoped)
    (settings.MEDIA_ROOT / str(value.id) / "attachments").mkdir(parents=True, exist_ok=True)
    directory, resources = None, []
    context = frozen
    if frozen.get("resources"):
        destination = settings.DATA_DIR / "analysis-context" / str(value.id) / frozen["snapshot_id"]
        context = materialize_context(frozen, destination)
        directory = str(destination)
        resources = [
            {"version_id": r["version_id"], "path": r["relative_path"], "sha256": r["sha256"]}
            for r in context["resources"]
        ]
    skills = catalog(session.connection)
    secrets = configured_secrets()
    message = value.messages.get(pk=job.payload["message_id"])
    latest = value.versions.order_by("-number").first()
    data = {
        "message": message.content,
        "attachments": list(value.attachments.values("name", "content_type")),
    }
    if latest and session.usage.get("last_result") != latest.number:
        data["previous_analysis"] = {
            "version": latest.number,
            "status": latest.status,
            "summary": latest.explanation.get("summary", ""),
            "baseline": latest.baseline,
            "limits": latest.evidence.get("limitations", []),
            "applies_only_to_its_frozen_context": True,
        }
    instructions = (
        "You are the instance's single conversational assistant. Discuss the user's project naturally. "
        "Answer the latest question, ask only useful factual clarifications and accept corrections. "
        "Prefer a short direct answer; provide detail when requested. You may inspect granted read-only "
        "sources and documents. Never invent observed behavior or hide tool/access errors. "
        "This is informal discussion, NOT independent verification. Treat your earlier messages as "
        "unverified hypotheses. Do not claim to have performed three-role review. Never create or "
        "publish a ticket, goal or change any resource. Never turn a factual clarification into a "
        "normative business decision. The user can explicitly launch deep analysis separately. "
        "Return the Markdown response in message, as JSON matching the schema. No private reasoning."
    )
    db = frozen.get("dossier", {}).get("database", {})
    database = parameters(DatabaseConnection.objects.get(pk=db["id"])) if db.get("id") else None
    native = session.runtime_id or None
    for attempt in range(2):
        if not live(job):
            return
        turn = copy.deepcopy(data)
        if not native:
            turn.update(
                recovery=recovery_messages(value, message.pk), frozen_project_context=context
            )
        prompt = redact(
            RULES
            + "\n"
            + instructions
            + "\n"
            + output_language_instruction(value.language)
            + "\n"
            + session.connection.additional_instructions
            + "\n"
            + registry_instructions(skills.get("registry", []))
            + "\nUNTRUSTED CONVERSATION DATA:\n"
            + json.dumps(turn, ensure_ascii=False),
            secrets,
        )
        if len(prompt) > 190000:
            raise ValueError("Discussion context is too large. Start a focused conversation.")
        try:
            result = caller(
                "/run",
                {
                    "request_id": str(value.pk),
                    "context_id": str(session.context_id),
                    "attempt_id": job.payload["attempt_id"],
                    "persistent_conversation": True,
                    "independent_context": True,
                    "session_id": native,
                    "agent": session.agent,
                    "model": session.model_snapshot,
                    "reasoning_effort": session.reasoning_effort_snapshot,
                    "identity_id": job.payload["assignment"]["credential_id"],
                    "profile": "code",
                    "phase": "analysis",
                    "web_references": True,
                    "public_role": "discussion",
                    "workspace": str(workspace),
                    "repositories": [r["repository"] for r in scoped.baseline],
                    "context_dir": directory,
                    "context_resources": resources,
                    "database": database,
                    "skill_definitions": redact(skills.get("definitions", []), secrets),
                    "prompt": prompt,
                    "schema": Reply.model_json_schema(),
                    "timeout": 260,
                },
                timeout=270,
            )
        except ProviderUnavailable as exc:
            if exc.kind == "SESSION_UNAVAILABLE" and native and attempt == 0:
                native = None
                session.context_id, session.runtime_id = uuid.uuid4(), ""
                session.save(update_fields=["context_id", "runtime_id"])
                with transaction.atomic():
                    locked_job = Job.objects.select_for_update().get(pk=job.pk)
                    if locked_job.status != "RUNNING":
                        return
                    notice(
                        value,
                        "The native session could not be resumed. A new session is using the saved conversation.",
                    )
                continue
            raise
        if result.get("cancelled") or not live(job):
            return
        if result.get("timed_out"):
            raise TimeoutError("Discussion response interrupted")
        output = Reply.model_validate(redact(result.get("output"), secrets))
        # A successful conversational response must carry a real resumable identity.
        native_result = str(uuid.UUID(result.get("session_id") or ""))
        with transaction.atomic():
            locked_job = Job.objects.select_for_update().get(pk=job.pk)
            locked = Request.objects.select_for_update().get(pk=value.pk)
            if (
                locked_job.status != "RUNNING"
                or locked.discussion_state.get("revision") != job.payload["revision"]
            ):
                return
            session.runtime_id = native_result
            session.usage = {
                **result.get("usage", {}),
                "last_result": latest.number if latest else None,
            }
            session.save(update_fields=["runtime_id", "usage"])
            if native and native_result != native:
                notice(
                    locked,
                    "The provider returned a different native session. The application history is preserved; native continuity could not be confirmed.",
                )
            RequestMessage.objects.create(
                request=locked,
                role="assistant",
                kind="discussion_reply",
                content=output.message,
                data={
                    "session_pk": session.pk,
                    "revision": job.payload["revision"],
                    "native_resumed": bool(native and native_result == native),
                    "native_session_id": native_result,
                    "context_id": str(session.context_id),
                    "connection_id": session.connection_id,
                    "provider": session.agent,
                    "model": result.get("model") or session.model_snapshot,
                    "verified": False,
                    "observations": redact(
                        {
                            key: result[key]
                            for key in (
                                "context_usage",
                                "database_checks",
                                "web_checks",
                                "permission_limits",
                                "permission_events",
                                "loaded_skills",
                                "skills_audit",
                            )
                            if key in result
                        },
                        secrets,
                    ),
                },
            )
            locked.status, locked.error = "DISCUSSING", ""
            locked.save(update_fields=["status", "error", "updated_at"])
            Job.objects.filter(pk=job.pk).update(status="DONE", finished_at=timezone.now())
        return


def fail(job, message):
    with transaction.atomic():
        locked_job = Job.objects.select_for_update().get(pk=job.pk)
        if locked_job.status != "RUNNING":
            return
        value = Request.objects.select_for_update().get(pk=job.target)
        value.status, value.error = "ERROR", message
        value.save(update_fields=["status", "error", "updated_at"])
        Job.objects.filter(pk=job.pk).update(
            status="ERROR", error=message, finished_at=timezone.now()
        )


def recover_cancellations():
    """Hold the shared quota lease until the exact runtime attempt acknowledges stop."""
    from .providers import release_connections

    for job in Job.objects.filter(kind=KIND, status="CANCELLED").exclude(
        payload__connection_ids=[]
    ):
        try:
            result = runtime_call(
                "/runs/cancel",
                {"request_id": job.target, "attempt_id": job.payload["attempt_id"]},
                timeout=10,
            )
        except ValueError:
            continue
        if result.get("stopped") is True:
            with transaction.atomic():
                locked = Job.objects.select_for_update().get(pk=job.pk)
                release_connections(locked.payload.get("connection_ids", []))
                locked.payload["connection_ids"] = []
                locked.payload.pop("awaiting_stop", None)
                locked.save(update_fields=["payload"])


def stop_failed_attempt(job):
    """Uncertain transport/process failures cannot free a still executing provider lease."""
    try:
        result = runtime_call(
            "/runs/cancel",
            {"request_id": job.target, "attempt_id": job.payload["attempt_id"]},
            timeout=10,
        )
    except ValueError:
        result = {}
    if result.get("stopped") is True:
        return True
    job.payload["awaiting_stop"] = True
    Job.objects.filter(pk=job.pk).update(status="CANCELLED", payload=job.payload)
    return False


def activity_snapshot():
    """Reuse Activity's public card shape without creating analysis-role progress."""
    from django.db.models import OuterRef, Subquery

    from .analysis_titles import analysis_title

    latest = Job.objects.filter(kind=KIND, target=OuterRef("target")).order_by("-id")
    jobs = list(
        Job.objects.filter(kind=KIND, pk=Subquery(latest.values("pk")[:1]))
        .exclude(status="DONE")
        .order_by("-id")[:100]
    )
    values = {str(r.pk): r for r in Request.objects.filter(pk__in=[j.target for j in jobs])}
    rows = []
    for job in jobs:
        value = values.get(job.target)
        if value is None or value.discussion_state.get("mode") != "discussion":
            continue
        state = (
            "WAITING_AI"
            if job.status == "QUEUED" and job.payload.get("waiting_reason")
            else job.status
        )
        if value.status == "ERROR":
            state = "ERROR"
        rows.append(
            {
                "id": job.pk,
                "kind": KIND,
                "request_id": str(value.pk),
                "workflow": value.workflow,
                "title": analysis_title(value),
                "status": job.status,
                "queue_state": state,
                "request_status": value.status,
                "analysis_state": "waiting_ai" if state == "WAITING_AI" else "processing",
                "requires_attention": value.status == "ERROR",
                "can_cancel": job.status in BUSY,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "href": f"/analyses/{value.pk}",
                "waiting_reason": job.payload.get("waiting_reason", ""),
                "queue_position": None,
                "assignments": [],
                "environment_name": value.environment_name_snapshot,
                "operation": "Discussion",
                "agent": None,
            }
        )
    return rows


@router.post("/analyses/{analysis_id}/discussion")
def message(request, analysis_id: uuid.UUID, payload: MessageIn):
    from .api import request_dict

    return request_dict(enqueue(analysis_id, payload, actor(request)), full=True)


@router.post("/analyses/{analysis_id}/deep-analyze")
@transaction.atomic
def deepen(request, analysis_id: uuid.UUID, payload: DeepIn):
    from .api import request_dict
    from .services import queue_run

    value = get_object_or_404(
        Request.objects.select_for_update(of=("self",)).select_related("environment__database"),
        pk=analysis_id,
    )
    idle(value)
    state = value.discussion_state
    if payload.expected_revision != state.get("revision", 0):
        raise HttpError(409, "The conversation changed. Refresh before starting deep analysis.")
    if value.validated_version:
        raise HttpError(409, "Reopen the validated request before starting another analysis.")
    if payload.intent == "change" and not value.versions.exists():
        value.workflow, value.intent_mode = "request", "explicit"
    pin_environment(value)
    value.analysis_protocol, value.confrontation, value.status = "2.4", True, "DRAFT"
    state.update(enabled=True, mode="analysis", analyzed_revision=state.get("revision", 0))
    value.discussion_state = state
    value.save()
    value = queue_run(value)
    return request_dict(value, full=True)


@router.post("/analyses/{analysis_id}/cancel")
def cancel_deep(request, analysis_id: uuid.UUID):
    from .api import request_dict
    from .step_execution import cancel_analysis

    return request_dict(cancel_analysis(analysis_id), full=True)


@router.post("/analyses/{analysis_id}/discussion/cancel")
@transaction.atomic
def cancel(request, analysis_id: uuid.UUID):
    from .api import request_dict

    return request_dict(cancel_jobs(analysis_id), full=True)


@transaction.atomic
def cancel_jobs(analysis_id):
    jobs = list(
        Job.objects.select_for_update().filter(kind=KIND, target=str(analysis_id), status__in=BUSY)
    )
    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id)
    for job in jobs:
        job.status, job.finished_at = "CANCELLED", timezone.now()
        job.save(update_fields=["status", "finished_at"])
    if jobs:
        value.status, value.error = "CANCELLED", ""
        value.save(update_fields=["status", "error", "updated_at"])
    return value
