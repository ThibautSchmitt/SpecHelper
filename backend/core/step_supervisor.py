"""A small local process supervisor; database leases coordinate multiple workers."""

import os
import signal
import subprocess
import sys
import time
import uuid

from django.conf import settings
from django.utils import timezone

from .models import Job, StepExecution
from .step_execution import ExecutionStopped, active_execution, wait_or_retry

OWNER = str(uuid.uuid4())
PROCESSES = {}


def start_invocation(job):
    from .step_execution import is_incremental

    if not is_incremental(job):
        process = subprocess.Popen(
            [sys.executable, str(settings.BASE_DIR / "manage.py"), "process_job", str(job.pk)],
            start_new_session=True,
        )
        PROCESSES[job.pk] = (process, None, time.monotonic())
        return
    step = active_execution(job)
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                str(settings.BASE_DIR / "manage.py"),
                "process_job",
                str(job.pk),
                "--attempt-id",
                str(step.attempt_id),
            ],
            start_new_session=True,
        )
    except OSError:
        wait_or_retry(job, step.attempt_id, "The worker could not start this step.", failed=True)
        return
    StepExecution.objects.filter(pk=step.pk, attempt_id=step.attempt_id, status="RUNNING").update(
        owner=OWNER, process_id=process.pid, heartbeat_at=timezone.now()
    )
    PROCESSES[job.pk] = (process, str(step.attempt_id), time.monotonic())


def stop_tree(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def stop_runtime(job, attempt_id):
    from .agent import runtime_call

    try:
        result = runtime_call(
            "/runs/cancel", {"request_id": job.target, "attempt_id": str(attempt_id)}, timeout=10
        )
        return result.get("stopped") is True
    except ValueError:
        return False


def poll_processes():
    from .providers import release_connections

    for job_id, (process, attempt_id, started) in list(PROCESSES.items()):
        job = Job.objects.get(pk=job_id)
        if job.kind == "discussion" and job.status == "CANCELLED":
            if stop_runtime(job, job.payload["attempt_id"]):
                if process.poll() is None:
                    stop_tree(process)
                release_connections(job.payload.get("connection_ids", []))
                job.payload["connection_ids"] = []
                job.save(update_fields=["payload"])
                PROCESSES.pop(job_id, None)
            continue
        if attempt_id is None:
            limit = 1200 if job.kind in {"sync", "cli_update"} else 295
            if process.poll() is None and time.monotonic() - started < limit:
                continue
            if process.poll() is None:
                stop_tree(process)
            PROCESSES.pop(job_id, None)
            if job.status == "RUNNING":
                from .worker import fail_analysis

                if job.kind == "analysis":
                    fail_analysis(job, "Analysis process interrupted.")
                elif job.kind == "discussion":
                    from .discussion import fail, stop_failed_attempt

                    fail(job, "The discussion was interrupted. Retry with a new session; history is preserved.")
                    if not stop_failed_attempt(job):
                        continue
                elif job.kind == "library_assistant":
                    from .library_assistant import fail_job

                    fail_job(
                        job, "Assistant work interrupted. Check the selected connection and retry."
                    )
                elif job.kind == "cli_update":
                    # Recovery reads the maintenance journal and rolls back if needed.
                    # Process exit alone cannot establish which executable is active.
                    continue
                else:
                    Job.objects.filter(pk=job_id, status="RUNNING").update(
                        status="ERROR",
                        error="Synchronization process interrupted",
                        finished_at=timezone.now(),
                    )
            release_connections(job.payload.get("connection_ids", []))
            continue
        if job.status == "CANCELLED":
            stopped = stop_runtime(job, attempt_id)
            if process.poll() is None:
                stop_tree(process)
            if stopped:
                release_connections(job.payload.get("connection_ids", []))
                job.payload["connection_ids"] = []
                job.save(update_fields=["payload"])
                PROCESSES.pop(job_id, None)
            continue
        if process.poll() is None:
            # This guards a stuck invocation/tool process, never total business-job age.
            if time.monotonic() - started <= 900:
                StepExecution.objects.filter(
                    job_id=job_id, attempt_id=attempt_id, status="RUNNING"
                ).update(heartbeat_at=timezone.now())
                continue
            if not stop_runtime(job, attempt_id):
                continue
            stop_tree(process)
        PROCESSES.pop(job_id, None)
        try:
            if StepExecution.objects.filter(
                job_id=job_id, attempt_id=attempt_id, status="RUNNING"
            ).exists():
                if not stop_runtime(job, attempt_id):
                    continue
                run = job.analysis_run
                if run.request.versions.filter(run=run).exists():
                    from .step_execution import complete_invocation

                    complete_invocation(job, attempt_id)
                else:
                    wait_or_retry(
                        job, attempt_id, "Interrupted step; preserved checkpoints will be reused."
                    )
        except ExecutionStopped:
            pass
