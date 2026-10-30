"""Deletion hides dossiers without erasing immutable publication provenance."""

from uuid import uuid4

import pytest

from core.models import (
    AnalysisRun,
    GeneratedArtifact,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
    StepExecution,
    TicketConnector,
)

pytestmark = pytest.mark.django_db


def remove(client, value, **body):
    return client.delete(f"/api/analyses/{value.pk}", {"confirmed": True, **body}, content_type="application/json")


@pytest.mark.parametrize("workflow", ["request", "question"])
def test_deletion_hides_all_views_and_legacy_outputs_but_keeps_other_analyses(client, environment, workflow):
    value = Request.objects.create(environment=environment, need="Remove this test", workflow=workflow, status="NEEDS_CLARIFICATION")
    other = Request.objects.create(environment=environment, need="Keep this", status="READY")
    RequestMessage.objects.create(request=value, role="user", kind="need", content=value.need)
    version = ResultVersion.objects.create(request=value, number=1)
    GeneratedArtifact.objects.create(version=version, name="goal.md", content="Saved evidence")
    job = Job.objects.create(kind="analysis", target=str(value.pk), status="DONE")
    AnalysisRun.objects.create(request=value, job=job, number=1, status="NEEDS_CLARIFICATION")
    assert remove(client, value, confirmed=False).status_code == 422
    assert Request.objects.filter(pk=value.pk).exists()
    assert remove(client, value).status_code == 200
    assert remove(client, value).status_code == 200
    assert Request.all_objects.get(pk=value.pk).deleted_at
    assert not Request.objects.filter(pk=value.pk).exists()
    assert list(Request.objects.values_list("pk", flat=True)) == [other.pk]
    assert RequestMessage.objects.filter(request=value).count() == 1
    assert ResultVersion.objects.filter(pk=version.pk).exists()
    assert client.get("/api/analyses").json()["total"] == 1
    overview = client.get("/api/analyses/overview").json()
    assert all(item["id"] != str(value.pk) for item in overview["recent"])
    legacy = "questions" if workflow == "question" else "requests"
    artifact = "answer.md" if workflow == "question" else "goal.md"
    for path in (f"/analyses/{value.pk}", f"/{legacy}/{value.pk}", f"/{legacy}/{value.pk}/versions/1", f"/{legacy}/{value.pk}/versions/1/artifacts/{artifact}"):
        assert client.get("/api" + path).status_code == 404
    assert client.post(f"/api/{legacy}/{value.pk}/analyze").status_code == 404
    from core.queue import snapshot

    assert str(value.pk) not in str(snapshot())
    assert client.get(f"/api/analyses/{other.pk}").status_code == 200


@pytest.mark.parametrize("status", ["QUEUED", "ANALYZING", "REVIEWING", "CONTINUING_CONVERSATION"])
def test_active_analysis_requires_cancellation(client, environment, status):
    value = Request.objects.create(environment=environment, need="Busy", status=status)
    assert remove(client, value).status_code == 409
    assert Request.objects.filter(pk=value.pk).exists()


def test_cancelled_analysis_cannot_disappear_while_runtime_still_runs(client, environment):
    value = Request.objects.create(environment=environment, need="Stopping", status="CANCELLED")
    job = Job.objects.create(kind="analysis", target=str(value.pk), status="CANCELLED")
    step = StepExecution.objects.create(job=job, checkpoint="analyst", public_role="analyst", status="RUNNING")
    assert remove(client, value).status_code == 409
    StepExecution.objects.filter(pk=step.pk).update(status="CANCELLED")
    Job.objects.filter(pk=job.pk).update(payload={"connection_ids": [1]})
    assert remove(client, value).status_code == 409
    Job.objects.filter(pk=job.pk).update(payload={"connection_ids": []})
    assert remove(client, value).status_code == 200


def test_published_tickets_and_derived_evolutions_remain_accessible(client, environment):
    value = Request.objects.create(environment=environment, need="Published source", status="READY")
    version = ResultVersion.objects.create(request=value, number=1)
    derived = Request.objects.create(environment=environment, need="Follow-up", source_question_version=version)
    connector = TicketConnector.objects.create(environment=environment, platform="gitlab", base_url="https://example.test")
    connector.environments.add(environment)
    ticket = PublishedTicket.objects.create(request=value, version=version, connector=connector, status="PUBLISHED", idempotency_key=uuid4(), external_reference="fixture:delete")
    assert remove(client, value).status_code == 200
    response = client.get(f"/api/tickets/{ticket.pk}")
    assert response.status_code == 200 and response.json()["analysis_deleted"] is True
    assert client.get(f"/api/analyses/{derived.pk}").status_code == 200
    assert PublishedTicket.objects.get(pk=ticket.pk).request.pk == value.pk


def test_publication_in_progress_blocks_deletion(client, environment):
    value = Request.objects.create(environment=environment, need="Publishing", status="READY")
    version = ResultVersion.objects.create(request=value, number=1)
    connector = TicketConnector.objects.create(environment=environment, platform="gitlab", base_url="https://example.test")
    connector.environments.add(environment)
    PublishedTicket.objects.create(request=value, version=version, connector=connector, status="PUBLISHING", idempotency_key=uuid4(), external_reference="fixture:busy")
    assert remove(client, value).status_code == 409
