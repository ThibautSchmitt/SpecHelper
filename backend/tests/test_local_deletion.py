"""Local deletion preserves conversation, publication provenance and write fences."""

import uuid
from unittest.mock import Mock

import pytest
from ninja.errors import HttpError

from core.local_deletion import delete_run, remove_publication
from core.models import (
    AISession,
    AnalysisRun,
    ConversationTicket,
    GeneratedArtifact,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
    StepExecution,
    TicketConnector,
)
from core.ticket_preparation import verified

pytestmark = pytest.mark.django_db


def cycle(value, number, status="DONE"):
    job = Job.objects.create(kind="analysis", target=str(value.pk), status=status)
    run = AnalysisRun.objects.create(request=value, job=job, number=number, status="READY")
    version = ResultVersion.objects.create(
        request=value,
        run=run,
        number=number,
        status="READY",
        evidence={"claims": [{"status": "supported"}]},
    )
    GeneratedArtifact.objects.create(version=version, name="report.md", content="Frozen evidence")
    RequestMessage.objects.create(
        request=value, version=version, role="assistant", kind="result", content="Result"
    )
    return run, version, job


def publication(value, version, connector, **kwargs):
    return PublishedTicket.objects.create(
        request=value,
        version=version,
        connector=connector,
        platform="gitlab",
        project="1",
        destination=str(uuid.uuid4()),
        idempotency_key=uuid.uuid4(),
        external_reference="spechelper:" + str(uuid.uuid4()),
        payload_hash="frozen-digest",
        external_id=str(uuid.uuid4()),
        title="Ticket",
        body="Long content",
        status="PUBLISHED",
        **kwargs,
    )


def test_delete_one_cycle_keeps_conversation_other_cycle_and_frozen_ticket(environment):
    value = Request.objects.create(environment=environment, need="Dates", analysis_protocol="2.4")
    run, version, _ = cycle(value, 1)
    _, second, _ = cycle(value, 2)
    draft = ConversationTicket.objects.create(
        request=value, source_version=version, draft={"title": "Manual correction"}
    )
    connector = TicketConnector.objects.create(
        name="Test", platform="gitlab", base_url="https://gitlab.example"
    )
    published = publication(value, version, connector)
    message = RequestMessage.objects.create(
        request=value, role="user", kind="discussion", content="Independent"
    )
    assert delete_run(value.pk, 1) == {"status": "DELETED"}
    assert delete_run(value.pk, 1) == {"status": "DELETED"}
    assert Request.objects.filter(pk=value.pk).exists()
    assert list(value.analysis_runs.values_list("number", flat=True)) == [2]
    assert list(value.versions.values_list("pk", flat=True)) == [second.pk]
    assert RequestMessage.objects.filter(pk=message.pk).exists()
    published.refresh_from_db()
    draft.refresh_from_db()
    assert published.version.pk == version.pk
    assert published.version.artifacts.get().content == "Frozen evidence"
    assert draft.draft["title"] == "Manual correction"
    assert not verified(published.version)
    assert AnalysisRun.all_objects.get(pk=run.pk).steps == []


def test_unreferenced_results_are_deleted_and_number_is_reserved(environment):
    value = Request.objects.create(environment=environment, need="Dates")
    run, version, job = cycle(value, 1)
    assert delete_run(value.pk, 1)["status"] == "DELETED"
    retired = ResultVersion.all_objects.get(pk=version.pk)
    assert retired.deleted_at and retired.evidence == {}
    assert not GeneratedArtifact.objects.exists()
    assert AnalysisRun.all_objects.get(pk=run.pk).number == 1
    assert Job.objects.filter(pk=job.pk).exists()  # supervisor may still own its PID


def test_active_delete_waits_for_runtime_then_fences_late_completion(environment, monkeypatch):
    value = Request.objects.create(
        environment=environment, need="Dates", analysis_protocol="2.4", status="ANALYZING"
    )
    run, _, job = cycle(value, 1, "RUNNING")
    session = AISession.objects.create(request=value, role="analyst")
    step = StepExecution.objects.create(
        job=job,
        checkpoint="analyst",
        public_role="analyst",
        status="RUNNING",
        session=session,
        attempts=1,
    )
    runtime = Mock(return_value={"stopped": False})
    monkeypatch.setattr("core.agent.runtime_call", runtime)
    assert delete_run(value.pk, 1)["status"] == "STOPPING"
    step.refresh_from_db()
    job.refresh_from_db()
    assert step.status == job.status == "CANCELLED"
    assert AnalysisRun.objects.filter(pk=run.pk).exists()
    runtime.side_effect = lambda path, *args, **kwargs: (
        {"stopped": True} if path == "/runs/cancel" else {"released": True}
    )
    assert delete_run(value.pk, 1)["status"] == "DELETED"
    assert not AISession.objects.filter(pk=session.pk).exists()
    from core.step_execution import ExecutionStopped, active_execution

    with pytest.raises(ExecutionStopped):
        active_execution(job, step.attempt_id)


def test_retirement_is_local_per_publication_and_keeps_duplicate_keys(environment):
    value = Request.objects.create(environment=environment, need="Dates")
    _, version, _ = cycle(value, 1)
    connector = TicketConnector.objects.create(
        name="Test", platform="gitlab", base_url="https://gitlab.example"
    )
    first, second = publication(value, version, connector), publication(value, version, connector)
    RequestMessage.objects.create(
        request=value,
        role="assistant",
        kind="ticket_publication",
        content="Ticket published",
        data={"publication_id": str(first.pk)},
    )
    key = first.idempotency_key
    assert remove_publication(first.pk)["status"] == "REMOVED"
    assert remove_publication(first.pk)["status"] == "REMOVED"
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.removed_at and not second.removed_at
    assert first.idempotency_key == key and first.payload_hash == "frozen-digest"
    assert first.body == "" and not value.messages.filter(kind="ticket_publication").exists()


@pytest.mark.parametrize("state", ["PUBLISHING", "UNCERTAIN", "ERROR"])
def test_retirement_cannot_hide_unresolved_writes(environment, state):
    value = Request.objects.create(environment=environment, need="Dates")
    _, version, _ = cycle(value, 1)
    connector = TicketConnector.objects.create(
        name="Test", platform="gitlab", base_url="https://gitlab.example"
    )
    row = publication(value, version, connector)
    PublishedTicket.objects.filter(pk=row.pk).update(status=state)
    with pytest.raises(HttpError):
        remove_publication(row.pk)


def test_confirmation_is_required(client, environment):
    value = Request.objects.create(environment=environment, need="Dates")
    run, _, _ = cycle(value, 1)
    response = client.delete(
        f"/api/analyses/{value.pk}/runs/1", {"confirmed": False}, content_type="application/json"
    )
    assert response.status_code == 422
    assert AnalysisRun.objects.filter(pk=run.pk).exists()


def test_exclusive_materialized_context_is_removed_but_shared_workspace_survives(
    environment, storage
):
    value = Request.objects.create(environment=environment, need="Dates")
    run, _, _ = cycle(value, 1)
    identifier = str(uuid.uuid4())
    run.context_snapshot = {"snapshot_id": identifier}
    run.save(update_fields=["context_snapshot"])
    materialized = storage / "analysis-context" / str(value.pk) / identifier
    materialized.mkdir(parents=True)
    (materialized / "document.md").write_text("Only this cycle")
    workspace = storage / "analysis-workspaces" / str(value.pk)
    workspace.mkdir(parents=True)
    (workspace / "keep.py").write_text("Shared source")
    delete_run(value.pk, 1)
    assert not materialized.exists()
    assert (workspace / "keep.py").exists()


def test_retired_publication_disappears_from_api_and_cannot_be_republished(
    client, environment, monkeypatch
):
    value = Request.objects.create(environment=environment, need="Dates")
    _, version, _ = cycle(value, 1)
    connector = TicketConnector.objects.create(
        name="Test", platform="gitlab", base_url="https://gitlab.example"
    )
    first = publication(value, version, connector)
    second = publication(value, version, connector)
    endpoint = f"/api/tickets/{first.pk}"
    assert (
        client.delete(endpoint, {"confirmed": "yes"}, content_type="application/json").status_code
        == 422
    )
    assert (
        client.delete(endpoint, {"confirmed": True}, content_type="application/json").status_code
        == 200
    )
    ids = {item["id"] for item in client.get("/api/tickets").json()["items"]}
    assert str(first.pk) not in ids and str(second.pk) in ids
    assert client.get(endpoint).status_code == 404
    remote = Mock(side_effect=AssertionError("No provider should be called"))
    monkeypatch.setattr("core.ticket_publication.provider_for", remote)
    from core.ticket_publication import publish

    payload = {
        "confirmed": True,
        "project": "1",
        "title": "Ticket",
        "body": "Original",
        "fields": {},
        "labels": [],
        "assignees": [],
        "template_id": "",
        "issue_type": "",
        "options_revision": "",
        "idempotency_key": first.idempotency_key,
    }
    with pytest.raises(HttpError) as failure:
        publish(version, connector, payload)
    assert failure.value.status_code == 409
    remote.assert_not_called()
