"""Hour-long invocations remain bounded and explicit retries retain checkpoints."""

import copy
import importlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import connection
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
@pytest.mark.parametrize("checkpoint,role", [("analyst", "analyst"), ("verifier", "verifier")])
@pytest.mark.parametrize("saved_timeout", [300, 600])
def test_pending_checkpoint_upgrades_only_the_old_five_minute_budget(
    environment, checkpoint, role, saved_timeout
):
    from core.step_supervisor import process_timeout

    InstanceSettings.objects.update_or_create(
        pk=1, defaults={"orchestration": {"tool_timeout_seconds": 3600}}
    )
    value = Request.objects.create(environment=environment, analysis_protocol="2.4", need="Explain contract dates.")
    enqueue_analysis(value.pk)
    run = value.analysis_runs.get()
    run.orchestration["config"]["tool_timeout_seconds"] = saved_timeout
    run.orchestration["config"]["timeout_seconds"] = saved_timeout
    run.orchestration["outputs"]["requirement"] = {"retained": "completed observation"}
    run.save(update_fields=["orchestration"])
    frozen, original_outputs = copy.deepcopy(run.context_snapshot), copy.deepcopy(run.orchestration["outputs"])
    job = run.job
    job.payload.update(next_checkpoint=checkpoint, current_role=role)
    job.save(update_fields=["payload"])
    job = claim_job()
    assert job is not None
    run.refresh_from_db()
    expected = 3600 if saved_timeout == 300 else saved_timeout
    assert run.orchestration["config"]["tool_timeout_seconds"] == expected
    assert process_timeout(job) == expected + 60
    assert run.orchestration["outputs"] == original_outputs
    assert run.context_snapshot == frozen
    assert job.executions.get(status="RUNNING").checkpoint == checkpoint
    if saved_timeout == 300:
        assert run.orchestration["execution_policy_history"][-1]["previous_timeout_seconds"] == 300
    else:
        assert not run.orchestration.get("execution_policy_history")


@pytest.mark.django_db
@pytest.mark.parametrize("saved_timeout", [300, 600, 3600, None])
def test_timeout_migration_preserves_custom_settings_and_completed_analysis_history(saved_timeout):
    config = {"global_instructions": "Keep this policy.", "v24_legacy_configuration": {"tool_timeout_seconds": 300}}
    if saved_timeout is not None:
        config["tool_timeout_seconds"] = saved_timeout
    settings, _ = InstanceSettings.objects.update_or_create(pk=1, defaults={"orchestration": config})
    value = Request.objects.create(need="Historical analysis.")
    historical = AnalysisRun.objects.create(
        request=value, number=1, status="DONE",
        orchestration={"config": {"tool_timeout_seconds": 300}, "outputs": {"verifier": {"retained": True}}},
        steps=[{"public_role": "verifier", "status": "DONE", "timeout_seconds": 300}],
    )
    original = copy.deepcopy(historical.orchestration), copy.deepcopy(historical.steps)
    migrate = importlib.import_module("core.migrations.0056_hour_long_ai_invocations").upgrade_timeout
    migrate(apps, SimpleNamespace(connection=connection))
    migrate(apps, SimpleNamespace(connection=connection))
    settings.refresh_from_db()
    expected = {**config, "tool_timeout_seconds": 3600} if saved_timeout == 300 else config
    assert settings.orchestration == expected
    from core.orchestration_settings import get_config

    assert get_config("2.4")["tool_timeout_seconds"] == (3600 if saved_timeout in {None, 300} else saved_timeout)
    historical.refresh_from_db()
    assert (historical.orchestration, historical.steps) == original


@pytest.mark.django_db
def test_legacy_timeout_refresh_never_changes_an_active_attempt(environment):
    from core.step_execution import reserve_step

    InstanceSettings.objects.update_or_create(pk=1, defaults={"orchestration": {"tool_timeout_seconds": 3600}})
    value = Request.objects.create(environment=environment, analysis_protocol="2.4", need="Explain contract dates.")
    enqueue_analysis(value.pk)
    run = value.analysis_runs.get()
    run.orchestration["config"]["tool_timeout_seconds"] = 300
    run.save(update_fields=["orchestration"])
    StepExecution.objects.create(job=run.job, checkpoint="verifier", public_role="verifier", status="RUNNING")
    assert reserve_step(run.job) is False
    run.refresh_from_db()
    assert run.orchestration["config"]["tool_timeout_seconds"] == 300
    assert not run.orchestration.get("execution_policy_history")


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
