"""Atomic checkpoint reservations and fenced, sequential execution within shared jobs."""

import contextlib
import copy
import hashlib
import threading
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from ninja.errors import HttpError

from .models import AnalysisRun, Job, Request, StepExecution

NO_PROGRESS = (
    "The analysis could not advance to a new validated step. Completed observations are preserved."
)


class StepYield(Exception):
    """The current invocation completed; another ready checkpoint needs a lease."""

    def __init__(self, checkpoint, public_role):
        self.checkpoint, self.public_role = checkpoint, public_role


class ExecutionStopped(Exception):
    """A cancelled or superseded attempt cannot mutate current workflow state."""


@contextlib.contextmanager
def heartbeat(job, attempt_id):
    """The executing child proves liveness independently of scheduler polling."""
    from django.db import close_old_connections

    stopped = threading.Event()

    def update():
        try:
            while not stopped.wait(5):
                close_old_connections()
                if not StepExecution.objects.filter(
                    job=job, attempt_id=attempt_id, status="RUNNING"
                ).update(heartbeat_at=timezone.now()):
                    return
        finally:
            close_old_connections()

    thread = threading.Thread(target=update, daemon=True, name="step-heartbeat")
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=6)


def is_incremental(job):
    return job.kind == "analysis" and job.payload.get("analysis_protocol") == "2.4"


def invalidate_superseded_steps(job, outputs):
    """Completed work without a retained checkpoint must not block a new input revision."""
    job.executions.filter(status="DONE").exclude(checkpoint__in=list(outputs)).update(status="INVALIDATED")


def upgrade_pending(job):
    """Transition a migration-marked pending job without losing its frozen baseline/history."""
    from .orchestration_settings import get_config

    request = Request.objects.select_for_update().get(pk=job.target)
    run = AnalysisRun.objects.select_for_update().filter(job=job).first()
    if run is None:
        from django.db.models import Max

        from .environment_context import freeze_context

        run = AnalysisRun.objects.create(
            request=request,
            job=job,
            number=(request.analysis_runs.aggregate(last=Max("number"))["last"] or 0) + 1,
        )
        freeze_context(request, run, reuse=request.context_snapshot or None)
    old = copy.deepcopy(run.orchestration)
    old["context_snapshot"] = copy.deepcopy(run.context_snapshot)
    outputs = {}
    for name, value in old.get("outputs", {}).items():
        if name in {"requirement", "attachments", "focused_verification"}:
            if not value.get("questions"):
                outputs[name] = value
        elif name in {"analyst", "counter_independent"} and value.get("claims"):
            outputs[name] = {
                **value,
                "coverage": {
                    "inspected_areas": ["Previously recorded source observations"],
                    "new_elements": [],
                    "unexplored_zones": [
                        {
                            "id": "legacy-coverage",
                            "area": "Independent omission coverage before the queue transition",
                            "reason": "Earlier observations do not establish the new coverage review.",
                            "material": True,
                        }
                    ],
                },
            }
        elif name == "comparison" and not value.get("questions"):
            outputs[name] = value
    order = [("requirement", "analyst")]
    if request.attachments.exists():
        order.append(("attachments", "analyst"))
    order += [
        ("analyst", "analyst"),
        ("counter_independent", "counter_analyst"),
        ("comparison", "counter_analyst"),
    ]
    if outputs.get("comparison", {}).get("verification"):
        order.append(("focused_verification", "counter_analyst"))
    order += [("verifier", "verifier"), ("writer", "verifier")]
    # Later observations cannot stand in for missing prerequisites.
    checkpoint, role = next((name, role) for name, role in order if name not in outputs)
    first_missing = [name for name, _ in order].index(checkpoint)
    outputs = {name: outputs[name] for name, _ in order[:first_missing] if name in outputs}
    sessions = {
        role: session_id
        for role, session_id in old.get("sessions", {}).items()
        if (role == "analyst" and "analyst" in outputs)
        or (role == "counter_analyst" and "counter_independent" in outputs)
    }
    run.orchestration = {
        "version": "2.4",
        "config": get_config("2.4"),
        "outputs": outputs,
        "sessions": sessions,
        "calls": 0,
        "legacy_execution_snapshot": old,
        "database_checks": copy.deepcopy(old.get("database_checks", [])),
        "query_roles": copy.deepcopy(old.get("query_roles", {})),
        "waiting_role": role,
        "waiting_reason": "",
    }
    from .models import AISession

    captured_connections = {}
    for session_id, snapshot in old.get("connection_snapshots", {}).items():
        if str(session_id).isdigit():
            connection_id = (
                AISession.objects.filter(pk=session_id)
                .values_list("connection_id", flat=True)
                .first()
            )
            if connection_id:
                text = snapshot.get("additional_instructions", "")
                captured_connections.setdefault(
                    str(connection_id),
                    {
                        "additional_instructions": text,
                        "version": hashlib.sha256(text.encode()).hexdigest(),
                    },
                )
    run.orchestration["connection_instruction_snapshots"] = captured_connections
    request.analysis_protocol, request.confrontation = "2.4", True
    request.save(update_fields=["analysis_protocol", "confrontation"])
    from .environment_context import freeze_context

    freeze_context(request, run, reuse=run.context_snapshot or None)
    run.save(update_fields=["orchestration"])
    job.payload.update(
        analysis_protocol="2.4",
        requires_step_upgrade=False,
        next_checkpoint=checkpoint,
        current_role=role,
        connection_ids=[],
    )
    job.save(update_fields=["payload"])


def active_execution(job, attempt_id=None):
    attempt_id = attempt_id or job.payload.get("attempt_id")
    value = StepExecution.objects.filter(job=job, attempt_id=attempt_id, status="RUNNING").first()
    if value is None or not Job.objects.filter(pk=job.pk, status="RUNNING").exists():
        raise ExecutionStopped()
    return value


def check_execution(run):
    if run.job_id:
        return active_execution(run.job, getattr(run, "execution_attempt", None))


@contextlib.contextmanager
def fenced_transition(run):
    """Use the same short lock order as cancellation; never hold it over inference."""
    with transaction.atomic():
        Job.objects.select_for_update().get(pk=run.job_id)
        Request.objects.select_for_update().get(pk=run.request_id)
        check_execution(run)
        yield


def save_run(run, update_fields):
    if run.job_id and run.request.analysis_protocol == "2.4":
        with fenced_transition(run):
            run.save(update_fields=update_fields)
    else:
        run.save(update_fields=update_fields)


@transaction.atomic
def reserve_step(job):
    """Called with the job locked. Reserve only its next checkpoint and quota group."""
    from .global_skills import catalog
    from .orchestration import RoleUnavailable, assign_role

    request = Request.objects.select_for_update().get(pk=job.target)
    if (
        Job.objects.filter(kind="analysis", target=job.target, status="RUNNING")
        .exclude(pk=job.pk)
        .exists()
    ):
        return False
    run = AnalysisRun.objects.select_for_update().get(job=job)
    state = run.orchestration
    checkpoint = job.payload.get("next_checkpoint", "requirement")
    role = job.payload.get("current_role", "analyst")
    if StepExecution.objects.filter(job=job, status="RUNNING").exists():
        return False
    step, _ = StepExecution.objects.get_or_create(
        job=job, checkpoint=checkpoint, defaults={"public_role": role}
    )
    try:
        session = assign_role(request, run, role)
    except RoleUnavailable as wait:
        job.refresh_from_db()
        job.payload.update(waiting_reason=wait.reason, current_role=role)
        job.save(update_fields=["payload"])
        return False
    connection = session.connection
    state = run.orchestration
    snapshots = state.setdefault("connection_instruction_snapshots", {})
    key = str(connection.pk)
    if key not in snapshots:
        snapshots[key] = {
            "additional_instructions": connection.additional_instructions,
            "version": hashlib.sha256(connection.additional_instructions.encode()).hexdigest(),
        }
    database_checkpoint = checkpoint in {
        "analyst",
        "counter_independent",
        "comparison",
        "verifier",
    } or (
        checkpoint == "focused_verification"
        and state.get("outputs", {}).get("comparison", {}).get("verification", {}).get("target")
        == "code"
    )
    from .skill_metadata import CAPABILITIES

    available_capabilities = CAPABILITIES - ({"read_web"} if not database_checkpoint else set())
    skill_snapshot = catalog(
        connection,
        bool(request.database_snapshot) and database_checkpoint,
        available_capabilities=available_capabilities,
    )
    instruction_snapshot = {
        "native_analysis_policy": state["config"].get("native_analysis_policy", ""),
        "global_instructions": state["config"].get("global_instructions", ""),
        "global_instruction_version": state["config"].get("global_instruction_version", 1),
        "connection_instructions": copy.deepcopy(snapshots[key]),
        "public_role": role,
    }
    step.status, step.attempt_id = "RUNNING", uuid.uuid4()
    step.attempts += 1
    step.public_role, step.session, step.connection = role, session, connection
    step.instruction_snapshot, step.skill_snapshot = instruction_snapshot, skill_snapshot
    step.loaded_skills = []
    step.started_at, step.heartbeat_at, step.finished_at = timezone.now(), timezone.now(), None
    step.owner, step.process_id, step.error = "", None, ""
    step.save()
    run.orchestration = state
    run.save(update_fields=["orchestration"])
    job.refresh_from_db()
    job.payload.update(
        attempt_id=str(step.attempt_id),
        step_execution_id=step.pk,
        current_role=role,
        next_checkpoint=checkpoint,
        waiting_reason="",
    )
    job.save(update_fields=["payload"])
    return True


@transaction.atomic
def complete_invocation(job, attempt_id, pending=None):
    """Checkpoint output and next scheduling state commit under the same fence."""
    from .providers import release_connections

    job = Job.objects.select_for_update().get(pk=job.pk)
    step = active_execution(job, attempt_id)
    run = AnalysisRun.objects.select_for_update().get(job=job)
    step.output = run.orchestration.get("outputs", {}).get(step.checkpoint, {})
    from .models import ResultVersion

    published = ResultVersion.objects.filter(run=run).exists()
    stalled = (
        not step.output
        or pending.checkpoint == step.checkpoint
        or pending.checkpoint in run.orchestration.get("outputs", {})
        or job.executions.filter(checkpoint=pending.checkpoint, status="DONE").exists()
    ) if pending else run.status != "NEEDS_CLARIFICATION"
    if stalled and not published:
        # Only accepted checkpoint output or a terminal business result advances
        # the graph. Provider waiting and independent roles are never duplicates.
        step.save(update_fields=["output"])
        wait_or_retry(job, attempt_id, NO_PROGRESS, failed=True)
        return
    if published:
        pending = None
    step.status, step.finished_at = "DONE", timezone.now()
    step.save(update_fields=["output", "status", "finished_at"])
    release_connections(job.payload.get("connection_ids", []), job=job)
    job.payload["connection_ids"] = []
    if pending:
        job.status = "QUEUED"
        job.payload.update(
            next_checkpoint=pending.checkpoint, current_role=pending.public_role, waiting_reason=""
        )
        run.status = "QUEUED"
        run.orchestration.update(
            waiting_role=pending.public_role, waiting_reason="", checkpoint=pending.checkpoint
        )
        run.save(update_fields=["status", "orchestration"])
        Request.objects.filter(pk=job.target).update(status="QUEUED")
    else:
        job.status, job.finished_at = "DONE", timezone.now()
    job.save(update_fields=["status", "payload", "finished_at"])


@transaction.atomic
def wait_or_retry(job, attempt_id, message, failed=False):
    from .providers import release_connections

    job = Job.objects.select_for_update().get(pk=job.pk)
    Request.objects.select_for_update().get(pk=job.target)
    step = active_execution(job, attempt_id)
    from .models import ResultVersion

    if ResultVersion.objects.filter(run__job=job).exists():
        complete_invocation(job, attempt_id)
        return
    step.status = "ERROR" if failed else "QUEUED"
    step.error, step.finished_at = message, timezone.now()
    step.save(update_fields=["status", "error", "finished_at"])
    release_connections(job.payload.get("connection_ids", []), job=job)
    job.status = "ERROR" if failed else "QUEUED"
    job.error = message
    job.payload.update(connection_ids=[], waiting_reason=message)
    job.save(update_fields=["status", "error", "payload"])
    close_step_history(job, attempt_id, "ERROR" if failed else "INTERRUPTED")
    AnalysisRun.objects.filter(job=job).update(status=job.status, error=message)
    Request.objects.filter(pk=job.target).update(status=job.status, error=message if failed else "")


@transaction.atomic
def cancel_request(request_id):
    """Fence publication immediately; the supervisor/runtime stop the process tree."""
    jobs = list(
        Job.objects.select_for_update().filter(
            kind="analysis", target=str(request_id), status__in=["QUEUED", "RUNNING"]
        )
    )
    request = Request.objects.select_for_update().get(pk=request_id)
    if request.analysis_protocol != "2.4":
        raise HttpError(409, "This historical execution does not support cancellation.")
    if request.status in {"READY", "PARTIAL"}:
        raise HttpError(409, "This analysis is no longer running or waiting.")
    if not jobs:
        raise HttpError(409, "This analysis is no longer running or waiting.")
    attempts = []
    for job in jobs:
        for step in job.executions.filter(status="RUNNING"):
            attempts.append(str(step.attempt_id))
            close_step_history(job, step.attempt_id, "CANCELLED")
        job.executions.filter(status__in=["RUNNING", "QUEUED"]).update(
            status="CANCELLED", finished_at=timezone.now()
        )
        job.status, job.finished_at = "CANCELLED", timezone.now()
        job.save(update_fields=["status", "finished_at"])
        AnalysisRun.objects.filter(job=job).update(status="CANCELLED", finished_at=timezone.now())
    request.status, request.error = "CANCELLED", ""
    request.save(update_fields=["status", "error", "updated_at"])
    return attempts


def close_step_history(job, attempt_id, status):
    run = AnalysisRun.objects.select_for_update().get(job=job)
    for entry in run.steps:
        if entry.get("attempt_id") == str(attempt_id) and entry.get("status") == "RUNNING":
            entry.update(status=status, finished_at=timezone.now().isoformat())
    run.save(update_fields=["steps"])


def acknowledge_cancellation(job):
    """A quota lease is released only after the exact remote attempt is stopped."""
    from .agent import runtime_call
    from .providers import release_connections

    attempts = job.executions.filter(status="CANCELLED", attempts__gt=0)
    for step in attempts:
        try:
            result = runtime_call(
                "/runs/cancel",
                {"request_id": job.target, "attempt_id": str(step.attempt_id)},
                timeout=10,
            )
            if result.get("stopped") is not True:
                return False
        except ValueError:
            return False
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job.pk)
        if job.status != "CANCELLED":
            return False
        release_connections(job.payload.get("connection_ids", []), job=job)
        job.payload["connection_ids"] = []
        job.save(update_fields=["payload"])
    return True


def cancel_analysis(request_id):
    if Job.objects.filter(kind="discussion", target=str(request_id), status__in=["QUEUED", "RUNNING"]).exists():
        from .discussion import cancel_jobs

        return cancel_jobs(request_id)
    cancel_request(request_id)
    for job in Job.objects.filter(kind="analysis", target=str(request_id), status="CANCELLED"):
        if job.payload.get("connection_ids"):
            acknowledge_cancellation(job)
    return Request.objects.get(pk=request_id)


def recover_steps(now=None):
    """A heartbeat, not total job age, identifies interrupted executions."""
    now = now or timezone.now()
    for job in Job.objects.filter(kind="analysis", status="CANCELLED"):
        if job.payload.get("connection_ids"):
            acknowledge_cancellation(job)
    candidates = StepExecution.objects.filter(
        status="RUNNING", heartbeat_at__lt=now - timedelta(seconds=45)
    )
    for candidate in candidates:
        # Cancellation of the exact runtime attempt precedes releasing its quota.
        from .agent import runtime_call

        try:
            result = runtime_call(
                "/runs/cancel",
                {"request_id": candidate.job.target, "attempt_id": str(candidate.attempt_id)},
                timeout=10,
            )
            if result.get("stopped") is not True:
                continue
        except ValueError:
            continue
        try:
            wait_or_retry(
                candidate.job,
                candidate.attempt_id,
                "Interrupted step; preserved checkpoints will be reused.",
            )
        except ExecutionStopped:
            continue


@transaction.atomic
def retry_analysis(request_id):
    """Explicitly retry the interrupted checkpoint, preserving prior source observations."""
    from .business_decisions import assert_editable

    request = Request.objects.select_for_update().get(pk=request_id)
    assert_editable(request)
    if request.status not in {"ERROR", "CANCELLED"}:
        raise HttpError(409, "Only an interrupted or cancelled analysis can be retried.")
    job = (
        Job.objects.select_for_update()
        .filter(kind="analysis", target=str(request_id))
        .order_by("-id")
        .first()
    )
    if not job or not is_incremental(job):
        raise HttpError(409, "Start a new analysis to use the current execution protocol.")
    if job.payload.get("connection_ids"):
        raise HttpError(409, "The previous execution is still stopping. Retry shortly.")
    run = AnalysisRun.objects.get(job=job)
    invalidate_superseded_steps(job, run.orchestration.get("outputs", {}))
    job.status, job.error, job.finished_at = "QUEUED", "", None
    job.payload["waiting_reason"] = ""
    job.save(update_fields=["status", "error", "finished_at", "payload"])
    AnalysisRun.objects.filter(job=job).update(status="QUEUED", error="", finished_at=None)
    request.status, request.error = "QUEUED", ""
    request.save(update_fields=["status", "error", "updated_at"])
    return request
