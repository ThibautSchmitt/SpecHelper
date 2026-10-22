import logging
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .agent import ProviderUnavailable, runtime_call
from .git import request_workspace, sync_environment
from .models import AnalysisRun, Job, Request, RequestMessage

logger = logging.getLogger(__name__)


def progress(request, status, label):
    request.status = status
    request.progress += [{"label": label, "at": timezone.now().isoformat()}]
    request.save(update_fields=["status", "progress", "updated_at"])


def analyze(request_id, run_id=None, deadline=None):
    from .analysis_flow import analyze as execute

    return execute(request_id, run_id, runtime_call, request_workspace, progress, deadline=deadline)


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
    from .providers import reserve_for_job

    with transaction.atomic():
        jobs = Job.objects.filter(status="QUEUED").order_by("created_at", "id")
        from django.db import connection

        if connection.features.has_select_for_update_skip_locked:
            jobs = jobs.select_for_update(skip_locked=True)
        for job in jobs[:100]:
            if job.kind == "analysis" and not reserve_for_job(job):
                continue
            if Job.objects.filter(pk=job.pk, status="QUEUED").update(
                status="RUNNING", started_at=timezone.now()
            ):
                job.payload["execution"] = job.payload.get("execution", 0) + 1
                job.save(update_fields=["payload"])
                return job


def recover_stale_jobs():
    from django.db.models import Q

    from .providers import release_connections

    stale = Job.objects.filter(status="RUNNING").filter(
        Q(kind="analysis", started_at__lt=timezone.now() - timedelta(seconds=310))
        | Q(kind="sync", started_at__lt=timezone.now() - timedelta(seconds=1210))
    )
    for job in stale:
        if job.kind == "analysis":
            fail_analysis(job, "Worker interrupted; analysis unfinished.")
            release_connections(job.payload.get("connection_ids", []))
            continue
        else:
            from .models import Environment

            Environment.objects.filter(pk=job.target).update(
                status="ERROR", error="Synchronization interrupted"
            )
        Job.objects.filter(pk=job.pk, status="RUNNING").update(
            status="ERROR", error="Worker interrupted", finished_at=timezone.now()
        )


def perform_job(job):
    try:
        if job.kind == "sync":
            sync_environment(int(job.target), job.payload.get("changed_repositories"))
        else:
            from .providers import release_connections, reserve_for_job

            run = AnalysisRun.objects.filter(job=job).first()
            deadline = time.monotonic() + 285
            for attempt in range(2):
                try:
                    analyze(job.target, run.pk if run else None, deadline=deadline)
                    break
                except ProviderUnavailable:
                    job.refresh_from_db()
                    release_connections(job.payload.get("connection_ids", []))
                    if attempt == 0 and reserve_for_job(job):
                        continue
                    # Provider waiting is queue time, not a failed business analysis.
                    Job.objects.filter(pk=job.pk).update(
                        status="QUEUED", started_at=None, finished_at=None
                    )
                    AnalysisRun.objects.filter(job=job).update(status="QUEUED", finished_at=None)
                    Request.objects.filter(pk=job.target).update(status="QUEUED", error="")
                    return

    except Exception as exc:
        logger.warning("Job %s failed (%s)", job.pk, type(exc).__name__)
        if job.kind == "sync":
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
        if job.kind == "analysis":
            fail_analysis(job, message)
            return
        Job.objects.filter(pk=job.pk).update(
            status="ERROR", error=message, finished_at=timezone.now()
        )
    else:
        Job.objects.filter(pk=job.pk).update(status="DONE", finished_at=timezone.now())
    finally:
        if job.kind == "analysis":
            from .providers import release_connections

            job.refresh_from_db()
            release_connections(job.payload.get("connection_ids", []))


def work_once():
    from .providers import (
        ensure_connections,
        recover_orphaned_leases,
        refresh_unknown_connections,
        release_connections,
    )

    recover_stale_jobs()
    recover_orphaned_leases()
    ensure_connections()
    refresh_unknown_connections(runtime_call)
    job = claim_job()
    if not job:
        return False
    # Bound the entire job, including Git preparation and a stuck HTTP/CLI subprocess.
    process = subprocess.Popen(
        [sys.executable, str(settings.BASE_DIR / "manage.py"), "process_job", str(job.id)],
        start_new_session=True,
    )
    try:
        process.wait(timeout=295 if job.kind == "analysis" else 1200)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        if job.kind == "analysis":
            fail_analysis(job, "The five-minute limit was reached.")
        else:
            from .models import Environment

            Environment.objects.filter(pk=job.target).update(
                status="ERROR", error="The synchronization time limit was reached."
            )
        if job.kind != "analysis":
            Job.objects.filter(pk=job.pk).update(
                status="ERROR", error="Time limit reached", finished_at=timezone.now()
            )
    if process.returncode and Job.objects.filter(pk=job.pk, status="RUNNING").exists():
        Job.objects.filter(pk=job.pk).update(
            status="ERROR", error="Process interrupted", finished_at=timezone.now()
        )
        if job.kind == "analysis":
            fail_analysis(job, "Analysis process interrupted.")
        else:
            from .models import Environment

            Environment.objects.filter(pk=job.target).update(
                status="ERROR", error="Synchronization process interrupted."
            )
    if job.kind == "analysis":
        job.refresh_from_db()
        release_connections(job.payload.get("connection_ids", []))
    return True
