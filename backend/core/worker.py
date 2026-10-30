import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .agent import ProviderUnavailable, runtime_call
from .git import request_workspace, sync_environment
from .models import AnalysisRun, ConnectionAttempt, InstanceSettings, Job, Request, RequestMessage

logger = logging.getLogger(__name__)


def progress(request, status, label):
    run = getattr(request, "execution_run", None)
    if run:
        from .step_execution import fenced_transition

        with fenced_transition(run):
            request.status = status
            request.progress += [{"label": label, "at": timezone.now().isoformat()}]
            request.save(update_fields=["status", "progress", "updated_at"])
        return
    request.status = status
    request.progress += [{"label": label, "at": timezone.now().isoformat()}]
    request.save(update_fields=["status", "progress", "updated_at"])


def analyze(request_id, run_id=None, deadline=None, attempt_id=None):
    from .analysis_flow import analyze as execute

    return execute(
        request_id,
        run_id,
        runtime_call,
        request_workspace,
        progress,
        deadline=deadline,
        attempt_id=attempt_id,
    )


@transaction.atomic
def fail_analysis(job, message):
    request = Request.objects.select_for_update().get(pk=job.target)
    run = AnalysisRun.objects.filter(job=job).first()
    # Publication commits the result and final states together. A later process
    # interruption must not turn a successfully published result into a failure.
    if run and run.status in {"READY", "PARTIAL", "NEEDS_CLARIFICATION"}:
        Job.objects.filter(pk=job.pk).update(status="DONE", finished_at=timezone.now())
        return
    request.status, request.error = "ERROR", message
    request.save(update_fields=["status", "error", "updated_at"])
    AnalysisRun.objects.filter(pk=run.pk if run else None).update(
        status="ERROR", error=message, finished_at=timezone.now()
    )
    RequestMessage.objects.create(request=request, role="assistant", kind="error", content=message)
    Job.objects.filter(pk=job.pk).update(status="ERROR", error=message, finished_at=timezone.now())


def claim_job():
    from .providers import capacity_reservations, reserve_for_job

    with transaction.atomic():
        # Serialize admission, not execution; maintenance drains running invocations.
        InstanceSettings.objects.get_or_create(pk=1)
        InstanceSettings.objects.select_for_update().get(pk=1)
        jobs = Job.objects.filter(status="QUEUED").order_by("created_at", "id")
        maintenance = Job.objects.filter(kind="cli_update", status__in=["QUEUED", "RUNNING"]).order_by("created_at", "id").first()
        if maintenance:
            if Job.objects.filter(status="RUNNING").exists() or capacity_reservations() or ConnectionAttempt.objects.filter(status__in=["STARTING", "AWAITING_USER"], expires_at__gt=timezone.now()).exists():
                return None
            jobs = jobs.filter(pk=maintenance.pk)
        from django.db import connection

        if connection.features.has_select_for_update_skip_locked:
            jobs = jobs.select_for_update(skip_locked=True)
        capacity_full = len(capacity_reservations()) >= settings.AI_CONCURRENCY
        for job in jobs.iterator(chunk_size=100):
            if job.kind in {"analysis", "discussion", "library_assistant"} and capacity_full:
                if job.payload.get("waiting_reason") != "Waiting for an AI execution slot.":
                    job.payload = {**job.payload, "waiting_reason": "Waiting for an AI execution slot."}
                    job.save(update_fields=["payload"])
                continue
            from .step_execution import is_incremental, reserve_step, upgrade_pending

            if job.payload.get("requires_step_upgrade"):
                upgrade_pending(job)

            if is_incremental(job):
                if not reserve_step(job):
                    continue
            elif job.kind in {"analysis", "library_assistant", "discussion"} and not reserve_for_job(job):
                continue
            if Job.objects.filter(pk=job.pk, status="QUEUED").update(
                status="RUNNING", started_at=job.started_at or timezone.now()
            ):
                job.payload["execution"] = job.payload.get("execution", 0) + 1
                job.save(update_fields=["payload"])
                return job


def recover_stale_jobs():
    from .cli_maintenance import recover_updates
    recover_updates()
    from django.db.models import Q

    from .providers import release_connections

    stale = Job.objects.filter(status="RUNNING").filter(
        Q(
            kind__in=["analysis", "library_assistant", "discussion"],
            started_at__lt=timezone.now() - timedelta(seconds=310),
        )
        | Q(kind="sync", started_at__lt=timezone.now() - timedelta(seconds=1210))
    )
    for job in stale:
        from .step_execution import is_incremental

        if is_incremental(job):
            continue
        if job.kind == "discussion":
            from .discussion import fail, stop_failed_attempt

            fail(job, "The discussion was interrupted. Retry with a new session; history is preserved.")
            if not stop_failed_attempt(job):
                continue
            release_connections(job.payload.get("connection_ids", []), job=job)
            continue
        if job.kind == "library_assistant":
            from .library_assistant import fail_job

            fail_job(job, "Worker interrupted; assistant work unfinished.")
            release_connections(job.payload.get("connection_ids", []), job=job)
            continue
        if job.kind == "analysis":
            fail_analysis(job, "Worker interrupted; analysis unfinished.")
            release_connections(job.payload.get("connection_ids", []), job=job)
            continue
        else:
            from .models import Environment

            Environment.objects.filter(pk=job.target).update(
                status="ERROR", error="Synchronization interrupted"
            )
        Job.objects.filter(pk=job.pk, status="RUNNING").update(
            status="ERROR", error="Worker interrupted", finished_at=timezone.now()
        )


def perform_job(job, attempt_id=None):
    from .orchestration import RoleUnavailable
    from .step_execution import is_incremental

    if is_incremental(job):
        return perform_invocation(job, attempt_id)

    try:
        if job.kind == "discussion":
            from .discussion import run_job

            run_job(job)
        elif job.kind == "sync":
            sync_environment(int(job.target), job.payload.get("changed_repositories"))
        elif job.kind == "cli_update":
            from .cli_maintenance import perform_update
            perform_update(job)
        elif job.kind == "library_assistant":
            from .library_assistant import run_job

            run_job(job)
        else:
            from .providers import release_connections, reserve_for_job

            run = AnalysisRun.objects.filter(job=job).first()
            deadline = time.monotonic() + 285
            from .models import AIConnection

            attempted = set()
            max_attempts = max(1, AIConnection.objects.filter(enabled=True).count())
            for attempt in range(max_attempts):
                try:
                    analyze(job.target, run.pk if run else None, deadline=deadline)
                    break
                except ProviderUnavailable as unavailable:
                    job.refresh_from_db()
                    attempted.update(job.payload.get("connection_ids", []))
                    release_connections(job.payload.get("connection_ids", []), job=job)
                    if attempt + 1 < max_attempts and reserve_for_job(job, exclude=attempted):
                        continue
                    # Provider waiting is queue time, not a failed business analysis.
                    message = (
                        "The selected model is unavailable for this AI connection. Choose an accepted model in Settings and retry."
                        if unavailable.kind == "MODEL_UNAVAILABLE"
                        else ""
                    )
                    Job.objects.filter(pk=job.pk).update(
                        status="QUEUED", started_at=None, finished_at=None, error=message
                    )
                    AnalysisRun.objects.filter(job=job).update(status="QUEUED", finished_at=None)
                    Request.objects.filter(pk=job.target).update(status="QUEUED", error="")
                    return

    except ProviderUnavailable as unavailable:
        if job.kind != "discussion":
            if job.kind == "library_assistant":
                from .library_assistant import fail_job

                fail_job(job, "Assistant work interrupted. Check the selected connection and retry.")
            elif job.kind == "analysis":
                fail_analysis(job, "Analysis interrupted. Check connections and the runtime.")
            return
        from .discussion import fail
        from .providers import mark_failure

        if unavailable.kind in {"BUSY", "QUOTA_EXHAUSTED", "AUTH_ERROR", "MODEL_UNAVAILABLE"}:
            mark_failure(job.payload["assignment"]["connection_id"], unavailable.kind,
                         unavailable.retry_seconds, unavailable.quota_windows)
            with transaction.atomic():
                changed = Job.objects.filter(pk=job.pk, status="RUNNING").update(status="QUEUED", started_at=None,
                    error="Waiting for the selected AI connection.")
                if changed:
                    Request.objects.filter(pk=job.target).update(status="QUEUED")
        else:
            fail(job, "The discussion response failed. Your messages are preserved; retry with a new session.")
    except RoleUnavailable as wait:
        Job.objects.filter(pk=job.pk).update(
            status="QUEUED", started_at=None, finished_at=None, error=wait.reason
        )
        AnalysisRun.objects.filter(job=job).update(status="QUEUED", finished_at=None)
        Request.objects.filter(pk=job.target).update(status="QUEUED", error="")
        job.refresh_from_db()
        job.payload = {**job.payload, "current_role": wait.role, "waiting_reason": wait.reason}
        job.save(update_fields=["payload"])
        return
    except Exception as exc:
        logger.warning("Job %s failed (%s)", job.pk, type(exc).__name__)
        if job.kind == "discussion":
            from .discussion import fail

            fail(job, "The discussion response failed. Your messages are preserved; retry with a new session.")
            return
        if job.kind == "cli_update":
            from .cli_maintenance import UpdateUncertain
            if isinstance(exc, UpdateUncertain):
                return
            message = str(exc) if isinstance(exc, ValueError) else "CLI update interrupted. Check the displayed version and retry."
        elif job.kind == "sync":
            from .models import Environment

            message = (
                Environment.objects.filter(pk=job.target).values_list("error", flat=True).first()
                or "Synchronization interrupted. Check connections and selected versions."
            )
        else:
            from .analysis_flow import FlowError

            message = (
                "The five-minute limit was reached. Narrow the scope of your request."
                if isinstance(exc, TimeoutError)
                else str(exc)
                if isinstance(exc, FlowError)
                else "Analysis interrupted. Check connections and the runtime."
            )
        if job.kind == "library_assistant":
            from .library_assistant import fail_job

            fail_job(job, "Assistant work interrupted. Check the selected connection and retry.")
            return
        if job.kind == "analysis":
            fail_analysis(job, message)
            return
        Job.objects.filter(pk=job.pk).update(
            status="ERROR", error=message, finished_at=timezone.now()
        )
    else:
        Job.objects.filter(pk=job.pk, status="RUNNING").update(
            status="DONE", finished_at=timezone.now()
        )
    finally:
        if job.kind in {"analysis", "library_assistant", "discussion"}:
            from .providers import release_connections

            job.refresh_from_db()
            can_release = True
            if job.kind == "discussion" and job.status in {"ERROR", "CANCELLED"}:
                from .discussion import stop_failed_attempt

                can_release = stop_failed_attempt(job)
            if can_release:
                release_connections(job.payload.get("connection_ids", []), job=job)
                if job.kind == "discussion":
                    job.payload["connection_ids"] = []
                    job.save(update_fields=["payload"])


def work_once():
    from .discussion import recover_cancellations

    recover_cancellations()
    from .providers import ensure_connections, recover_orphaned_leases, refresh_unknown_connections
    from .step_execution import recover_steps
    from .step_supervisor import poll_processes, start_invocation

    poll_processes()
    recover_steps()
    recover_stale_jobs()
    recover_orphaned_leases()
    ensure_connections()
    refresh_unknown_connections(runtime_call)
    job = claim_job()
    if not job:
        return False
    start_invocation(job)
    return True


def perform_invocation(job, attempt_id=None):
    """Run exactly one ready checkpoint; retain observations when the lease yields."""
    from .step_execution import (
        ExecutionStopped,
        StepYield,
        active_execution,
        complete_invocation,
        heartbeat,
        wait_or_retry,
    )

    attempt_id = attempt_id or job.payload.get("attempt_id")
    try:
        active_execution(job, attempt_id)
        run = AnalysisRun.objects.get(job=job)
        with heartbeat(job, attempt_id):
            analyze(job.target, run.pk, attempt_id=attempt_id)
        complete_invocation(job, attempt_id)
    except StepYield as pending:
        complete_invocation(job, attempt_id, pending)
    except ExecutionStopped:
        return
    except ProviderUnavailable:
        wait_or_retry(job, attempt_id, "Waiting for a compatible AI connection.")
    except Exception as exc:
        from .analysis_flow import FlowError

        message = (
            str(exc)
            if isinstance(exc, FlowError)
            else "The step was interrupted. Completed observations are preserved; explicit retry is required."
        )
        try:
            wait_or_retry(job, attempt_id, message, failed=True)
        except ExecutionStopped:
            pass
