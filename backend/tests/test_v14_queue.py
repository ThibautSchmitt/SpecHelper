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


def test_current_public_role_and_limited_diversity_are_shared_without_private_state(
    client, environment
):
    request = Request.objects.create(environment=environment, need="Compare evidence")
    job = Job.objects.create(kind="analysis", target=str(request.pk), status="RUNNING")
    warning = {
        "code": "LIMITED_DIVERSITY",
        "role": "counter_analyst",
        "message": "Independent sessions use one model family.",
    }
    run = AnalysisRun.objects.create(
        request=request,
        job=job,
        number=1,
        orchestration={
            "version": "1.5",
            "current_role": "counter_analyst",
            "private_checkpoint": "not-public",
        },
        warnings=[warning],
        steps=[
            {
                "connection_id": 1,
                "connection_name": "Analyst account",
                "provider": "codex",
                "model": "model-a",
                "public_role": "analyst",
                "status": "DONE",
            },
            {
                "connection_id": 2,
                "connection_name": "Counter account",
                "provider": "claude",
                "model": "model-b",
                "public_role": "counter_analyst",
                "model_family": "anthropic",
                "status": "RUNNING",
            },
        ],
    )
    response = client.get("/api/queue")
    item = response.json()[0]
    assert item["public_role"] == "counter_analyst"
    assert item["connection_name"] == "Counter account" and item["model"] == "model-b"
    assert item["assignments"][0]["model_family"] == "anthropic"
    assert item["warnings"] == [warning]
    assert "not-public" not in response.content.decode()
    run.orchestration.update(waiting_role="verifier", waiting_reason="Waiting for another family.")
    run.save(update_fields=["orchestration"])
    Job.objects.filter(pk=job.pk).update(status="QUEUED")
    item = client.get("/api/queue").json()[0]
    assert item["public_role"] == "verifier" and item["assignments"] == []
    assert item["waiting_reason"] == "Waiting for another family."
