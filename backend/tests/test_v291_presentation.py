"""Read-only UX metadata must not equate wall time or terminal jobs with AI work."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import AnalysisRun, Job, Request, RequestMessage, ResultVersion
from core.queue import analysis_timing


def test_active_time_excludes_thirteen_hours_of_clarification_and_resource_waits():
    now = timezone.now()
    start = now - timedelta(hours=14)
    end = start + timedelta(seconds=75)
    job = SimpleNamespace(status="DONE", started_at=start, created_at=start, finished_at=end)
    run = SimpleNamespace(finished_at=end, steps=[
        {"started_at": start.isoformat(), "finished_at": end.isoformat(), "status": "DONE"},
        {"started_at": (end-timedelta(seconds=5)).isoformat(), "finished_at": end.isoformat(), "status": "DONE"},
    ])
    timing = analysis_timing(job, run, True, now)
    assert timing == {"active_analysis_seconds": 75, "clarification_since": end, "queued_since": None}
    assert analysis_timing(job, run, True, now+timedelta(days=2)) == timing
    job.status = "QUEUED"
    assert analysis_timing(job, run, False, now)["active_analysis_seconds"] == 75
    assert analysis_timing(job, run, False, now)["queued_since"] is None


def test_live_step_time_and_unknown_history_are_not_fabricated():
    now = timezone.now()
    start = now-timedelta(seconds=12)
    job = SimpleNamespace(status="RUNNING", started_at=start, created_at=start, finished_at=None)
    run = SimpleNamespace(finished_at=None, steps=[{"started_at": start.isoformat(), "finished_at": None, "status": "RUNNING"}])
    assert analysis_timing(job, run, False, now)["active_analysis_seconds"] == 12
    run.steps = [{"started_at": "invalid", "status": "DONE"}]
    assert analysis_timing(job, run, False, now)["active_analysis_seconds"] is None
    job.status, job.started_at = "QUEUED", None
    assert analysis_timing(job, run, False, now)["queued_since"] == start


@pytest.mark.django_db
def test_home_and_queue_keep_partial_and_failure_states_honest(client, environment):
    row = Request.objects.create(environment=environment, status="PARTIAL", need="Explain cancellation.")
    job = Job.objects.create(kind="analysis", target=str(row.pk), status="DONE", finished_at=timezone.now())
    AnalysisRun.objects.create(request=row, job=job, number=1, status="PARTIAL")
    ResultVersion.objects.create(request=row, number=1, status="PARTIAL", evidence={"limitations": ["Verifier quota unavailable."]})
    listing = client.get("/api/analyses").json()["items"][0]
    assert listing["result_state"] == "partial"
    assert listing["result_limits"] == ["Verifier quota unavailable."]
    sections = client.get("/api/analyses/overview").json()["sections"]
    assert sections["clarify"]["count"] == 0 and sections["consult"]["count"] == 1
    assert sections["active"]["count"] == 0
    assert client.get("/api/queue").json()[0]["analysis_state"] == "partial"
    row.status = "ERROR"
    row.save(update_fields=["status"])
    assert client.get("/api/analyses").json()["items"][0]["result_state"] == "interrupted"
    assert Job.objects.get(pk=job.pk).status == "DONE"


@pytest.mark.django_db
def test_paused_queue_preserves_timestamp_without_creating_work(client, environment):
    end = timezone.now()-timedelta(hours=13)
    row = Request.objects.create(environment=environment, status="NEEDS_CLARIFICATION", need="Clarify the export.")
    job = Job.objects.create(kind="analysis", target=str(row.pk), status="DONE", finished_at=end)
    AnalysisRun.objects.create(request=row, job=job, number=1, status="NEEDS_CLARIFICATION", finished_at=end)
    value = client.get("/api/queue").json()[0]
    assert abs((parse_datetime(value["clarification_since"])-end).total_seconds()) < 0.001
    assert value["active_analysis_seconds"] is None
    assert value["analysis_state"] == "clarification"
    assert Job.objects.count() == 1


@pytest.mark.django_db
def test_queue_uses_the_latest_result_and_flags_a_later_need_revision(client, environment):
    row = Request.objects.create(environment=environment, status="READY", workflow="question", need="Explain the export.")
    job = Job.objects.create(kind="analysis", target=str(row.pk), status="DONE", finished_at=timezone.now())
    AnalysisRun.objects.create(request=row, job=job, number=1, status="READY")
    ResultVersion.objects.create(request=row, number=1, status="PARTIAL")
    ResultVersion.objects.create(request=row, number=2, status="READY")
    assert client.get("/api/queue").json()[0]["analysis_state"] == "completed"
    RequestMessage.objects.create(request=row, role="user", kind="need_revision", content="Include archived exports.")
    assert client.get("/api/queue").json()[0]["analysis_state"] == "needs_reassessment"
    assert row.versions.count() == 2 and Job.objects.count() == 1


@pytest.mark.django_db
def test_blocking_evidence_is_partial_even_when_historical_status_is_ready(client, environment):
    row = Request.objects.create(environment=environment, status="READY", need="Explain validation.")
    job = Job.objects.create(kind="analysis", target=str(row.pk), status="DONE", finished_at=timezone.now())
    AnalysisRun.objects.create(request=row, job=job, number=1, status="READY")
    ResultVersion.objects.create(request=row, number=1, status="READY", evidence={"blocking": True, "limitations": ["Independent verification is unfinished."]})
    assert client.get(f"/api/analyses/{row.pk}").json()["result_state"] == "partial"
    assert client.get("/api/analyses").json()["items"][0]["result_state"] == "partial"
    assert client.get("/api/analyses/overview").json()["sections"]["consult"]["count"] == 1
    queue = client.get("/api/queue").json()[0]
    assert queue["analysis_state"] == queue["result_status"] == "partial"
    assert queue["result_limits"] == ["Independent verification is unfinished."]
    row.refresh_from_db()
    assert row.status == "READY" and row.versions.get().status == "READY"
