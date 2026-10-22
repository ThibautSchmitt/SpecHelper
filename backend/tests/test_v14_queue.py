import pytest
from django.utils import timezone

from core.models import AIConnection, AnalysisRun, Job, Request

pytestmark = pytest.mark.django_db


def test_queue_uses_execution_snapshots_after_configuration_changes(client, environment):
    connection = AIConnection.objects.get(pk=1)
    request = Request.objects.create(environment=environment, need="Audit assignment")
    job = Job.objects.create(kind="analysis", target=str(request.pk), status="RUNNING")
    run = AnalysisRun.objects.create(
        request=request,
        job=job,
        number=1,
        steps=[
            {
                "connection_id": connection.pk,
                "connection_name": "First configuration",
                "provider": "codex",
                "model": "selected-model",
                "status": "DONE",
            }
        ],
    )
    AIConnection.objects.filter(pk=connection.pk).update(name="Changed name", model="new-model")
    item = client.get("/api/queue").json()[0]
    assert item["connection_name"] == "First configuration"
    assert item["model"] == "selected-model"
    assert item["assignments"][0]["connection_id"] == connection.pk
    assert "Changed name" not in str(item)
    Job.objects.filter(pk=job.pk).update(status="DONE", finished_at=timezone.now())
    detail = client.get(f"/api/requests/{request.pk}").json()
    assert detail["analysis_runs"][0]["steps"] == run.steps
    assert client.get("/api/queue").json()[0]["model"] == "selected-model"


def test_requeued_request_has_no_active_assignment_even_when_previous_attempt_is_auditable(
    client, environment
):
    request = Request.objects.create(environment=environment, need="Wait for capacity")
    job = Job.objects.create(
        kind="analysis",
        target=str(request.pk),
        payload={
            "assignments": [
                {
                    "connection_id": 1,
                    "connection_name": "Previous",
                    "model": "prior",
                    "agent": "codex",
                }
            ]
        },
    )
    AnalysisRun.objects.create(
        request=request,
        job=job,
        number=1,
        steps=[
            {
                "connection_id": 1,
                "connection_name": "Previous",
                "model": "prior",
                "provider": "codex",
                "status": "ERROR",
                "failure": "QUOTA_EXHAUSTED",
            }
        ],
    )
    item = client.get("/api/queue").json()[0]
    assert item["assignments"] == []
    assert item["connection_name"] is None and item["model"] is None and item["agent"] is None
    assert item["queue_position"] == 1
