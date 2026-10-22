"""Public queue reflects work state without changing FIFO execution."""

import pytest
from django.utils import timezone

from core.models import AnalysisRun, Job, Request

pytestmark = pytest.mark.django_db


def test_latest_question_clarification_stays_paused_outside_recent_history(client, environment):
    question = Request.objects.create(
        environment=environment,
        workflow="question",
        need="Explain validations",
        status="NEEDS_CLARIFICATION",
    )
    old = Job.objects.create(
        kind="analysis", target=str(question.pk), status="DONE", finished_at=timezone.now()
    )
    latest = Job.objects.create(
        kind="analysis", target=str(question.pk), status="DONE", finished_at=timezone.now()
    )
    for _ in range(20):
        Job.objects.create(
            kind="sync", target=str(environment.pk), status="DONE", finished_at=timezone.now()
        )
    queued = Job.objects.create(kind="analysis", target="missing")
    values = client.get("/api/queue").json()
    paused = next(v for v in values if v["id"] == latest.pk)
    assert paused["queue_state"] == "PAUSED" and paused["status"] == "DONE"
    assert paused["pause_reason"] == "A business answer is needed."
    assert paused["workflow"] == "question" and paused["href"].startswith("/questions/")
    assert len([v for v in values if v["queue_state"] == "PAUSED"]) == 1
    assert old.pk not in [v["id"] for v in values]
    assert values[0]["id"] == queued.pk and values[0]["queue_position"] == 1
    assert Job.objects.count() == 23
    assert Job.objects.get(pk=latest.pk).status == "DONE"
    # Answering resumes the ordinary job queue; no synthetic paused job survives.
    question.status = "QUEUED"
    question.save(update_fields=["status"])
    resumed = Job.objects.create(kind="analysis", target=str(question.pk))
    values = client.get("/api/queue").json()
    assert not any(v["queue_state"] == "PAUSED" for v in values)
    assert next(v for v in values if v["id"] == resumed.pk)["queue_position"] == 2


@pytest.mark.parametrize("workflow", ["request", "question"])
def test_live_step_assignment_is_current_for_all_engines(client, environment, workflow):
    request = Request.objects.create(
        environment=environment,
        workflow=workflow,
        need="Explain current export",
        status="ANALYZING",
        progress=[{"label": "Focused project analysis", "at": timezone.now().isoformat()}],
    )
    job = Job.objects.create(kind="analysis", target=str(request.pk), status="RUNNING")
    AnalysisRun.objects.create(
        request=request,
        job=job,
        number=1,
        steps=[
            {
                "status": "DONE",
                "connection_id": 1,
                "connection_name": "Old analyst",
                "provider": "codex",
                "model": "old",
                "public_role": "analyst",
            },
            {
                "status": "RUNNING",
                "connection_id": 2,
                "connection_name": "Current verifier",
                "provider": "claude",
                "model": "current",
                "public_role": "verifier",
            },
        ],
    )
    value = client.get("/api/queue").json()[0]
    assert value["assignment_state"] == "current" and value["public_role"] == "verifier"
    assert value["connection_name"] == "Current verifier" and value["agent"] == "claude"
    assert len(value["assignments"]) == 1 and value["assignments"][0]["public_role"] == "verifier"
    assert value["stage"] == "Focused project analysis"


def test_completed_step_and_stale_payload_are_explicitly_historical(client, environment):
    request = Request.objects.create(environment=environment, need="Review export")
    recorded = {
        "connection_id": 1,
        "connection_name": "Last analyst",
        "provider": "codex",
        "model": "selected",
        "context_id": "old",
        "public_role": "analyst",
        "status": "DONE",
    }
    job = Job.objects.create(
        kind="analysis",
        target=str(request.pk),
        status="RUNNING",
        payload={"current_assignment": {**recorded, "agent": "codex"}},
    )
    AnalysisRun.objects.create(request=request, job=job, number=1, steps=[recorded])
    value = client.get("/api/queue").json()[0]
    assert value["assignment_state"] == "previous" and value["connection_name"] == "Last analyst"
    Job.objects.filter(pk=job.pk).update(status="QUEUED")
    value = client.get("/api/queue").json()[0]
    assert value["assignment_state"] == "unassigned" and value["assignments"] == []
    assert value["agent"] is None and value["stage"] == "Waiting for a worker"


def test_sync_and_failures_have_truthful_executor_and_public_reason(client, environment):
    job = Job.objects.create(
        kind="sync",
        target=str(environment.pk),
        status="RUNNING",
        payload={"connection_ids": [1], "assignments": [{"agent": "codex"}]},
    )
    value = client.get("/api/queue").json()[0]
    assert value["executor_name"] == "Git synchronization" and value["assignments"] == []
    assert value["agent"] is None and value["stage"] == "Synchronizing repositories"
    Job.objects.filter(pk=job.pk).update(
        status="ERROR", error="The Git server is unavailable.", finished_at=timezone.now()
    )
    value = client.get("/api/queue").json()[0]
    assert value["queue_state"] == "ERROR" and value["error"] == "The Git server is unavailable."
