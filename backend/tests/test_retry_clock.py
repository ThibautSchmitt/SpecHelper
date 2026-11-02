"""Retry clocks exclude historical attempts and agree across public projections."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from core.models import AnalysisRun, Job, Request
from core.queue import analysis_timing


@pytest.mark.parametrize("legacy", [False, True])
def test_retry_clock_excludes_old_attempts_and_stops_during_waits(legacy):
    now = timezone.now()
    retry = now - timedelta(seconds=30)
    old_start = now - timedelta(hours=2)
    steps = [
        {"status": "ERROR", "started_at": old_start.isoformat(), "finished_at": (old_start + timedelta(minutes=5)).isoformat()},
        {"status": "DONE", "started_at": (retry + timedelta(seconds=5)).isoformat(), "finished_at": (retry + timedelta(seconds=10)).isoformat()},
        {"status": "RUNNING", "started_at": (now - timedelta(seconds=7)).isoformat()},
    ]
    job = SimpleNamespace(status="RUNNING", created_at=old_start, started_at=old_start, finished_at=None, payload={} if legacy else {"retry_requested_at": retry.isoformat()})
    run = SimpleNamespace(steps=steps, finished_at=None, orchestration={"execution_policy_history": [{"reason": "explicit_retry", "changed_at": retry.isoformat()}]} if legacy else {})
    clock = analysis_timing(job, run, False, now)["analysis_clock"]
    assert clock == {"seconds": 12, "observed_at": now.isoformat(), "running": True}
    job.status = "QUEUED"
    steps[-1].update(status="DONE", finished_at=now.isoformat())
    waiting = analysis_timing(job, run, False, now + timedelta(hours=3))
    assert waiting["analysis_clock"] == {**clock, "running": False}
    assert analysis_timing(job, run, False, now + timedelta(days=1)) == waiting
    assert len(run.steps) == 3 and run.steps[0]["started_at"] == old_start.isoformat()


def test_new_retry_without_steps_starts_at_zero():
    now = timezone.now()
    job = SimpleNamespace(status="QUEUED", created_at=now-timedelta(hours=2), started_at=None, finished_at=None, payload={"retry_requested_at": now.isoformat()})
    value = analysis_timing(job, None, False, now)
    assert value["analysis_clock"] == {"seconds": 0, "observed_at": now.isoformat(), "running": False}
    assert value["queued_since"] == now


@pytest.mark.django_db
def test_queue_and_conversation_return_the_same_current_retry_clock(client, environment, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr("core.queue.timezone.now", lambda: now)
    row = Request.objects.create(environment=environment, status="ANALYZING", need="Explain fictional dates.")
    retry = now-timedelta(seconds=20)
    old = now-timedelta(hours=2)
    job = Job.objects.create(kind="analysis", target=str(row.pk), status="RUNNING", started_at=old, payload={"retry_requested_at": retry.isoformat()})
    AnalysisRun.objects.create(request=row, job=job, number=1, status="RUNNING", started_at=old, steps=[
        {"status":"ERROR", "started_at":old.isoformat(), "finished_at":(old+timedelta(minutes=5)).isoformat()},
        {"status":"RUNNING", "public_role":"analyst", "started_at":(now-timedelta(seconds=7.3)).isoformat()},
    ])
    queue = client.get("/api/queue").json()[0]
    response = client.get(f"/api/analyses/{row.pk}/progress")
    assert response.status_code == 200, response.content
    progress = response.json()["work_progress"][0]
    assert queue["analysis_clock"] == progress["analysis_clock"]
    assert queue["analysis_clock"] == {"seconds":7.3, "observed_at":now.isoformat(), "running":True}
    assert queue["active_analysis_seconds"] == 7
