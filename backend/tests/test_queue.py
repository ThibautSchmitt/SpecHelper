import pytest
from django.test import Client
from django.utils import timezone

from core.models import AnalysisRun, Job, Request

pytestmark = pytest.mark.django_db


def test_activity_link_stays_valid_while_intent_is_inferred(client, environment):
    value = Request.objects.create(environment=environment, need="Explain exports.", intent_mode="auto")
    job = Job.objects.create(kind="analysis", target=str(value.pk))
    before = next(item for item in client.get("/api/queue").json() if item["id"] == job.pk)
    Request.objects.filter(pk=value.pk).update(workflow="question", understanding="Explain export selection.")
    after = next(item for item in client.get("/api/queue").json() if item["id"] == job.pk)
    assert before["href"] == after["href"] == f"/analyses/{value.pk}"
    assert client.get(f"/api/analyses/{value.pk}").json()["workflow"] == "question"


def test_queue_reflects_shared_fifo_and_updates_without_claiming_work(client, environment):
    first = Request.objects.create(environment=environment, need="First request", status="QUEUED")
    second = Request.objects.create(environment=environment, need="Second request", status="QUEUED")
    older = Job.objects.create(kind="analysis", target=str(first.pk), payload={"secret": "hidden"})
    newer = Job.objects.create(kind="analysis", target=str(second.pk))
    running = Job.objects.create(
        kind="sync", target=str(environment.pk), status="RUNNING", started_at=timezone.now()
    )
    one = client.get("/api/queue")
    other_browser = Client()
    assert one.status_code == 200
    assert one.json() == other_browser.get("/api/queue").json()
    values = one.json()
    assert [value["id"] for value in values] == [running.pk, older.pk, newer.pk]
    assert [value["queue_position"] for value in values] == [None, 1, 2]
    assert "hidden" not in one.content.decode()
    assert Job.objects.get(pk=older.pk).status == "QUEUED"
    first.status = "NEEDS_CLARIFICATION"
    first.save()
    Job.objects.filter(pk=older.pk).update(status="DONE", finished_at=timezone.now())
    values = other_browser.get("/api/queue").json()
    assert next(v for v in values if v["id"] == older.pk)["request_status"] == "NEEDS_CLARIFICATION"
    assert next(v for v in values if v["id"] == newer.pk)["queue_position"] == 1


def test_queue_caps_terminal_history_keeps_failed_tasks_and_real_provider(client, environment):
    request = Request.objects.create(environment=environment, need="Clarify export")
    for _ in range(20):
        Job.objects.create(
            kind="sync", target=str(environment.pk), status="DONE", finished_at=timezone.now()
        )
        # The panel now hides successful synchronization and groups by business item.
        previous = Request.objects.create(environment=environment, need="Earlier request")
        Job.objects.create(
            kind="analysis", target=str(previous.pk), status="DONE", finished_at=timezone.now()
        )
    job = Job.objects.create(
        kind="analysis",
        target=str(request.pk),
        status="ERROR",
        finished_at=timezone.now(),
        error="Analysis interrupted.",
    )
    AnalysisRun.objects.create(request=request, job=job, number=1, steps=[{"provider": "codex"}])
    values = client.get("/api/queue").json()
    assert len(values) == 15
    assert all(value["kind"] == "analysis" for value in values)
    assert values[0]["agent"] == "codex"
    assert values[0]["error"] == "Analysis interrupted."
    assert values[0]["href"] == f"/analyses/{request.pk}"


def test_deleted_queue_targets_and_tied_timestamps_are_safe(client):
    first = Job.objects.create(kind="analysis", target="missing")
    second = Job.objects.create(kind="sync", target="missing")
    Job.objects.filter(pk=second.pk).update(created_at=first.created_at)
    values = client.get("/api/queue").json()
    assert [v["id"] for v in values] == [first.pk, second.pk]
    assert all(v["request_id"] is None for v in values)


def test_completed_later_cycle_replaces_old_failure_in_activity_without_hiding_other_failures(client, environment):
    value = Request.objects.create(environment=environment, need="Explain rounding.", status="READY")
    old = Job.objects.create(kind="analysis", target=str(value.pk), status="ERROR", error="Old interruption", finished_at=timezone.now())
    AnalysisRun.objects.create(request=value, number=1, job=old, status="ERROR", error="Old interruption")
    completed = Job.objects.create(kind="analysis", target=str(value.pk), status="DONE", finished_at=timezone.now())
    AnalysisRun.objects.create(request=value, number=2, job=completed, status="READY")
    unrelated = Request.objects.create(environment=environment, need="An unrelated unresolved problem.", status="ERROR")
    failure = Job.objects.create(kind="analysis", target=str(unrelated.pk), status="ERROR", error="Still unresolved", finished_at=timezone.now())
    AnalysisRun.objects.create(request=unrelated, number=1, job=failure, status="ERROR")
    cards = client.get("/api/queue").json()
    assert old.pk not in {card["id"] for card in cards}
    assert next(card for card in cards if card["id"] == completed.pk)["queue_state"] == "DONE"
    assert next(card for card in cards if card["id"] == failure.pk)["requires_attention"]
    old.refresh_from_db()
    assert old.status == "ERROR" and old.error == "Old interruption"


def test_waiting_ai_cards_are_active_and_never_truncated_by_completed_history(client, environment):
    waiting = []
    for index in range(20):
        request = Request.objects.create(
            environment=environment,
            need=f"Waiting {index}",
            analysis_protocol="2.4",
            status="QUEUED",
        )
        waiting.append(Job.objects.create(kind="analysis", target=str(request.pk), payload={"waiting_reason": "No AI resource available"}))
        finished = Request.objects.create(
            environment=environment, need=f"Finished {index}", status="READY"
        )
        Job.objects.create(
            kind="analysis", target=str(finished.pk), status="DONE", finished_at=timezone.now()
        )
    values = client.get("/api/queue").json()
    assert [row["id"] for row in values[:20]] == [job.pk for job in waiting]
    assert all(row["queue_state"] == "WAITING_AI" for row in values[:20])
    assert len(values) == 35
    assert [row["queue_position"] for row in values[:20]] == list(range(1, 21))


def test_publication_activity_is_visible_without_entering_the_analysis_scheduler(
    client, environment, bundle
):
    import uuid

    from core.models import PublishedTicket, TicketConnector
    from core.results import publish

    request = Request.objects.create(environment=environment, need="Export contracts")
    version = publish(request.pk, None, bundle)
    connector = TicketConnector.objects.create(
        name="Team tracker", platform="gitlab", base_url="https://gitlab.example", projects=["1"]
    )
    publication = PublishedTicket.objects.create(
        request=request,
        version=version,
        connector=connector,
        platform="gitlab",
        project="1",
        destination="gitlab:https://gitlab.example:1",
        title="Export contracts",
        body="Validated ticket",
        payload_hash="a" * 64,
        idempotency_key=uuid.uuid4(),
        external_reference="spechelper:" + str(uuid.uuid4()),
    )
    values = client.get("/api/queue").json()
    value = next(v for v in values if v["id"] == "publication:" + str(publication.pk))
    assert value["status"] == "RUNNING"
    assert value["kind"] == "publication"
    assert value["agent"] is None
    assert value["href"] == f"/analyses/{request.pk}?version=1"
    assert not Job.objects.exists()
    PublishedTicket.objects.filter(pk=publication.pk).update(
        status="UNCERTAIN", error="Publication status is uncertain.", finished_at=timezone.now()
    )
    value = next(
        v
        for v in client.get("/api/queue").json()
        if v["id"] == "publication:" + str(publication.pk)
    )
    assert value["status"] == "ERROR"
    assert value["publication_status"] == "UNCERTAIN"
    from datetime import timedelta

    PublishedTicket.objects.filter(pk=publication.pk).update(
        status="PUBLISHING",
        error="",
        finished_at=None,
        updated_at=timezone.now() - timedelta(seconds=100),
    )
    history = client.get(f"/api/requests/{request.pk}/versions/1/publications").json()
    assert history[0]["status"] == "UNCERTAIN"
    value = next(
        v
        for v in client.get("/api/queue").json()
        if v["id"] == "publication:" + str(publication.pk)
    )
    assert value["status"] == "ERROR" and value["publication_status"] == "UNCERTAIN"
    assert value["started_at"] is None
    assert PublishedTicket.objects.get(pk=publication.pk).status == "PUBLISHING"
