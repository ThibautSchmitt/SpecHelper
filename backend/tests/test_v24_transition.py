"""Existing queued jobs retain identity, source snapshots and usable observations."""

import copy
import importlib
import uuid
from unittest.mock import patch

import pytest
from django.apps import apps

from core.models import AIConnection, AIIdentity, AISession, Job, Request
from core.services import enqueue_analysis
from core.worker import claim_job

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("workflow", ["request", "question"])
@pytest.mark.parametrize("state", ["ERROR", "CANCELLED"])
def test_public_retry_reuses_the_failed_checkpoint_and_rejects_duplicate_clicks(
    client, environment, workflow, state
):
    from core.step_execution import acknowledge_cancellation, cancel_request, wait_or_retry

    request = Request.objects.create(
        environment=environment,
        analysis_protocol="2.4",
        workflow=workflow,
        need="Explain the export scope.",
    )
    enqueue_analysis(request.pk)
    claimed = claim_job()
    before = claimed.executions.get()
    frozen = copy.deepcopy(claimed.analysis_run.context_snapshot)
    if state == "ERROR":
        wait_or_retry(claimed, before.attempt_id, "Technical interruption", failed=True)
        claimed.refresh_from_db()
        before.refresh_from_db()
        assert claimed.finished_at == before.finished_at
        assert claimed.analysis_run.finished_at == before.finished_at
    else:
        cancel_request(request.pk)
        with patch("core.agent.runtime_call", return_value={"stopped": True}):
            assert acknowledge_cancellation(claimed)
    base = "questions" if workflow == "question" else "requests"
    url = f"/api/{base}/{request.pk}/retry"
    response = client.post(url)
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "QUEUED"
    assert client.post(url).status_code == 409
    resumed = claim_job()
    after = resumed.executions.get()
    assert resumed.pk == claimed.pk and resumed.analysis_run.pk == claimed.analysis_run.pk
    assert resumed.finished_at is None and resumed.analysis_run.finished_at is None
    assert resumed.analysis_run.context_snapshot == frozen
    assert after.checkpoint == before.checkpoint
    assert after.attempt_id != before.attempt_id
    assert after.session.context_id != before.session.context_id


def test_waiting_for_ai_resources_keeps_the_cycle_open(environment):
    from core.step_execution import wait_or_retry

    request = Request.objects.create(
        environment=environment, analysis_protocol="2.4", need="Explain the selected scope."
    )
    enqueue_analysis(request.pk)
    job = claim_job()
    step = job.executions.get()
    wait_or_retry(job, step.attempt_id, "Waiting for an available AI resource.")
    job.refresh_from_db()
    step.refresh_from_db()
    assert job.status == "QUEUED" and job.finished_at is None
    assert job.analysis_run.finished_at is None
    assert step.finished_at is not None


def test_successful_retry_clears_conversation_and_activity_failure_without_erasing_history(
    client, environment, monkeypatch
):
    from core.models import AnalysisRun
    from core.question_outputs import QuestionOutput
    from core.results import publish
    from core.step_execution import wait_or_retry
    from core.worker import perform_job

    value = Request.objects.create(environment=environment, analysis_protocol="2.4", workflow="question", need="Explain rounding.", discussion_state={"enabled":True,"mode":"analysis","revision":1})
    enqueue_analysis(value.pk)
    run = value.analysis_runs.get()
    run.orchestration["outputs"] = {key: {"questions": [], "retained": True} for key in ("requirement", "analyst", "comparison")}
    run.steps = [{"public_role":role,"roles":["code" if role=="analyst" else "reviewer_writer"],"status":"DONE"} for role in ("analyst","counter_analyst")]
    run.save(update_fields=["orchestration","steps"])
    job = run.job
    job.payload.update(next_checkpoint="verifier",current_role="verifier")
    job.save(update_fields=["payload"])
    job = claim_job()
    failed = job.executions.get(status="RUNNING")
    run.refresh_from_db()
    run.steps.append({"public_role":"verifier","roles":["synthesis"],"status":"ERROR","diagnostic":"Previous timeout"})
    run.save(update_fields=["steps"])
    frozen = copy.deepcopy(run.context_snapshot)
    wait_or_retry(job, failed.attempt_id, "Previous timeout", failed=True)
    assert any(item["queue_state"] == "ERROR" for item in client.get("/api/queue").json())
    assert client.post(f"/api/questions/{value.pk}/retry").status_code == 200

    def completed(request_id, run_id, **kwargs):
        resumed = AnalysisRun.objects.get(pk=run_id)
        resumed.orchestration["outputs"]["verifier"] = {"questions": [], "report": {"blocking": False}}
        resumed.steps.append({"public_role":"verifier","roles":["synthesis"],"status":"DONE"})
        resumed.save(update_fields=["orchestration","steps"])
        publish(request_id, resumed, QuestionOutput(status="READY", answer={"title":"Rounding", "summary":"The recorded rounding rule applies."}))

    monkeypatch.setattr("core.worker.analyze", completed)
    perform_job(claim_job())
    run.refresh_from_db()
    job.refresh_from_db()
    # No source evidence was fabricated by this fixture: completion remains partial,
    # while the technical incident has been resolved by the explicit retry.
    assert run.status == "PARTIAL" and job.status == "DONE" and job.error == "", (run.error, job.error)
    assert run.context_snapshot == frozen and value.analysis_runs.count() == 1
    assert any(step.get("diagnostic") == "Previous timeout" for step in run.steps)
    details = client.get(f"/api/analyses/{value.pk}").json()
    assert details["analysis_runs"][0]["execution"]["status"] == "PARTIAL"
    assert details["analysis_runs"][0]["execution"]["all_stages_done"]
    card = next(item for item in client.get("/api/queue").json() if item["id"] == job.pk)
    assert card["queue_state"] == "DONE" and not card["requires_attention"]


def mark_pending():
    importlib.import_module("core.migrations.0031_mark_pending_steps").mark_pending(apps, None)


def ready():
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Explain the export scope.",
        "questions": [],
        "ticket": None,
        "complexity": "simple",
    }


def test_only_pending_legacy_analyses_are_marked_without_losing_payload():
    jobs = [
        Job.objects.create(
            kind=kind, target="fixture", status=status, payload={"retained": "original", **extra}
        )
        for kind, status, extra in [
            ("analysis", "QUEUED", {}),
            ("analysis", "RUNNING", {}),
            ("analysis", "DONE", {}),
            ("sync", "QUEUED", {}),
            ("analysis", "QUEUED", {"analysis_protocol": "2.4"}),
        ]
    ]
    mark_pending()
    mark_pending()
    for index, job in enumerate(jobs):
        job.refresh_from_db()
        assert job.payload["retained"] == "original"
        assert bool(job.payload.get("requires_step_upgrade")) == (index == 0)


def test_claim_transitions_same_job_and_retains_frozen_source_observations(environment):
    request = Request.objects.create(
        environment=environment, need="Explain export scope", analysis_protocol="2.3"
    )
    enqueue_analysis(request.pk)
    run = request.analysis_runs.get()
    job = run.job
    frozen = copy.deepcopy(run.context_snapshot)
    connection = AIConnection.objects.get(pk=1)
    historical = AISession.objects.create(
        request=request,
        connection=connection,
        agent="codex",
        role="historical",
        public_role="analyst",
        family_snapshot="openai",
    )
    analyst = {"claims": [{"id": "retained", "statement": "An existing qualified observation"}]}
    run.orchestration = {
        "version": "2.3",
        "outputs": {"requirement": ready(), "analyst": analyst},
        "deadline_at": "2000-01-01T00:00:00+00:00",
        "sessions": {"analyst": historical.pk},
        "connection_snapshots": {
            str(historical.pk): {"additional_instructions": "Original connection guidance"}
        },
    }
    run.save()
    AIConnection.objects.create(
        agent="claude",
        identity=AIIdentity.objects.create(
            agent="claude", credential_id=uuid.uuid4(), status="CONNECTED", availability="AVAILABLE"
        ),
        status="CONNECTED",
        availability="AVAILABLE",
        roles=["counter_analyst", "verifier"],
    )
    mark_pending()
    selected = claim_job()
    assert selected.pk == job.pk
    request.refresh_from_db()
    run.refresh_from_db()
    assert request.analysis_protocol == "2.4"
    assert request.baseline == frozen["dossier"]["baseline"]
    assert run.pk == selected.analysis_run.pk and request.analysis_runs.count() == 1
    assert run.context_snapshot["instructions"]["mode"] == "factual"
    assert run.orchestration["legacy_execution_snapshot"]["context_snapshot"] == frozen
    assert run.orchestration["outputs"]["analyst"]["claims"] == analyst["claims"]
    assert run.orchestration["outputs"]["analyst"]["coverage"]["unexplored_zones"][0]["material"]
    assert "deadline_at" not in {
        key for key in run.orchestration if key != "legacy_execution_snapshot"
    }
    step = job.executions.get(status="RUNNING")
    assert step.checkpoint == "counter_independent" and step.connection.agent == "claude"
    assert (
        run.orchestration["connection_instruction_snapshots"][str(connection.pk)][
            "additional_instructions"
        ]
        == "Original connection guidance"
    )


def test_unqualified_legacy_source_report_is_retained_for_audit_and_rechecked(environment):
    request = Request.objects.create(
        environment=environment, need="Explain exports", analysis_protocol="legacy"
    )
    enqueue_analysis(request.pk)
    run = request.analysis_runs.get()
    old = {"requirement": ready(), "analyst": {"current_behavior": "Unqualified earlier report"}}
    run.orchestration = {"outputs": old}
    run.save()
    mark_pending()
    assert claim_job().pk == run.job_id
    run.refresh_from_db()
    assert run.orchestration["legacy_execution_snapshot"]["outputs"] == old
    assert set(run.orchestration["outputs"]) == {"requirement"}
    assert run.job.executions.get(status="RUNNING").checkpoint == "analyst"
