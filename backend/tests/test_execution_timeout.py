"""Hour-long invocations remain bounded and explicit retries retain checkpoints."""

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.utils import timezone
from pydantic import ValidationError

from core.models import AnalysisRun, InstanceSettings, Job, Request, StepExecution
from core.orchestration_settings import GlobalOrchestrationIn
from core.services import enqueue_analysis
from core.worker import claim_job, perform_job
from runtime.antigravity import headless_command
from runtime.server import RunIn


def test_runtime_and_antigravity_accept_one_hour_but_keep_a_finite_ceiling():
    payload = {
        "request_id": str(uuid4()),
        "agent": "antigravity",
        "workspace": "/tmp/workspace",
        "prompt": "Fictional fixture",
        "schema": {"type": "object"},
        "timeout": 3600,
    }
    assert RunIn.model_validate(payload).timeout == 3600
    with pytest.raises(ValidationError):
        RunIn.model_validate({**payload, "timeout": 3601})
    assert "3600s" in headless_command("fixture-model", timeout=3600)
    assert GlobalOrchestrationIn().tool_timeout_seconds == 3600
    with pytest.raises(ValidationError):
        GlobalOrchestrationIn(tool_timeout_seconds=3601)


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["discussion", "library_assistant"])
def test_long_ai_turn_survives_supervisor_and_stale_job_recovery(kind, environment, monkeypatch):
    from core import step_supervisor
    from core.worker import recover_stale_jobs

    InstanceSettings.objects.update_or_create(pk=1, defaults={"orchestration":{"tool_timeout_seconds":3600}})
    request = Request.objects.create(environment=environment, need="Explain contract dates.")
    job = Job.objects.create(kind=kind, target=str(request.pk), status="RUNNING",
        started_at=timezone.now()-timedelta(minutes=30))
    process = Mock()
    process.poll.return_value = None
    stop = Mock()
    monkeypatch.setattr(step_supervisor, "PROCESSES", {job.pk: (process, None, 0)})
    monkeypatch.setattr(step_supervisor.time, "monotonic", lambda: 1800)
    monkeypatch.setattr(step_supervisor, "stop_tree", stop)
    assert step_supervisor.process_timeout(job) == 3660
    step_supervisor.poll_processes()
    recover_stale_jobs()
    job.refresh_from_db()
    assert job.status == "RUNNING" and job.pk in step_supervisor.PROCESSES
    stop.assert_not_called()


@pytest.mark.django_db
def test_hour_long_analysis_refreshes_heartbeat_then_stops_the_exact_expired_attempt(environment, monkeypatch):
    from core import step_supervisor

    request = Request.objects.create(environment=environment, need="Explain contract dates.")
    job = Job.objects.create(kind="analysis", target=str(request.pk), status="RUNNING",
        payload={"analysis_protocol":"2.4"})
    run = AnalysisRun.objects.create(request=request, job=job, number=1,
        orchestration={"config":{"tool_timeout_seconds":3600}})
    step = StepExecution.objects.create(job=job, checkpoint="requirement", public_role="analyst",
        status="RUNNING", heartbeat_at=timezone.now()-timedelta(minutes=30))
    process = Mock()
    process.poll.return_value = None
    stop, cancel, retry = Mock(), Mock(return_value=True), Mock()
    monkeypatch.setattr(step_supervisor, "PROCESSES", {job.pk:(process,str(step.attempt_id),0)})
    monkeypatch.setattr(step_supervisor.time, "monotonic", lambda: 1800)
    monkeypatch.setattr(step_supervisor, "stop_tree", stop)
    monkeypatch.setattr(step_supervisor, "stop_runtime", cancel)
    monkeypatch.setattr(step_supervisor, "wait_or_retry", retry)
    step_supervisor.poll_processes()
    step.refresh_from_db()
    assert step.heartbeat_at > timezone.now()-timedelta(seconds=5)
    cancel.assert_not_called()
    monkeypatch.setattr(step_supervisor.time, "monotonic", lambda: 3661)
    step_supervisor.poll_processes()
    cancel.assert_called_with(job, str(step.attempt_id))
    assert all(call.args == (job, str(step.attempt_id)) for call in cancel.call_args_list)
    stop.assert_called_once_with(process)
    retry.assert_called_once()
    assert job.pk not in step_supervisor.PROCESSES
    run.refresh_from_db()
    assert run.orchestration["config"]["tool_timeout_seconds"] == 3600


@pytest.mark.django_db
def test_timeout_is_explicit_and_retry_preserves_the_completed_requirement(
    client, environment, storage, monkeypatch
):
    calls = []

    def runtime(path, payload, **kwargs):
        assert path == "/run"
        calls.append(payload)
        assert payload["timeout"] == 3600
        assert kwargs["timeout"] > 3600
        if payload["profile"] == "requirement":
            return {
                "session_id": str(uuid4()),
                "output": {
                    "status": "READY_TO_ANALYZE",
                    "understanding": "Explain contract dates.",
                    "questions": [],
                    "ticket": None,
                    "complexity": "simple",
                },
            }
        return {"session_id": str(uuid4()), "timed_out": True}

    monkeypatch.setattr("core.worker.runtime_call", runtime)
    monkeypatch.setattr("core.worker.request_workspace", lambda value: storage)
    InstanceSettings.objects.update_or_create(
        pk=1, defaults={"orchestration": {"tool_timeout_seconds": 3600}}
    )
    value = Request.objects.create(
        environment=environment,
        workflow="question",
        analysis_protocol="2.4",
        need="Explain contract dates.",
    )
    enqueue_analysis(value.pk)
    for _ in range(4):
        pending = claim_job()
        if not pending:
            break
        perform_job(pending)
    value.refresh_from_db()
    job = Job.objects.get(target=str(value.pk))
    run = AnalysisRun.objects.get(job=job)
    assert value.status == job.status == "ERROR"
    assert "execution time limit" in job.error
    assert "interrupted" not in job.error
    assert len(calls) == 2
    assert StepExecution.objects.get(job=job, checkpoint="requirement").status == "DONE"
    assert run.steps[-1]["failure"] == "TIMEOUT" and run.steps[-1]["timeout_seconds"] == 3600
    frozen = run.context_snapshot.copy()
    original_start, original_steps = run.started_at, run.steps.copy()
    accepted = run.orchestration["outputs"]["requirement"].copy()
    run.orchestration["config"]["tool_timeout_seconds"] = 300
    run.save(update_fields=["orchestration"])
    response = client.post(f"/api/questions/{value.pk}/retry")
    assert response.status_code == 200, response.content
    run.refresh_from_db()
    job.refresh_from_db()
    assert job.status == "QUEUED"
    assert job.started_at is None and job.payload["retry_requested_at"]
    assert run.started_at == original_start and run.steps == original_steps
    assert run.orchestration["config"]["tool_timeout_seconds"] == 3600
    assert run.orchestration["execution_policy_history"][-1]["previous_timeout_seconds"] == 300
    assert run.orchestration["outputs"]["requirement"] == accepted
    assert run.context_snapshot == frozen and value.analysis_runs.count() == 1
    assert StepExecution.objects.get(job=job, checkpoint="requirement").status == "DONE"
