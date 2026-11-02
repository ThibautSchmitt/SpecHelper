"""Durable conversations, independently frozen cycles and separately owned tickets."""

import copy

import pytest
from django.utils import timezone

from core.analysis_flow import context
from core.models import (
    AISession,
    AnalysisRun,
    ConversationTicket,
    Job,
    Request,
    RequestMessage,
    ResultVersion,
)

pytestmark = pytest.mark.django_db


def conversation(environment):
    row = Request.objects.create(
        environment=environment,
        environment_name_snapshot=environment.name,
        need="Explain the benefit dates.",
        status="DISCUSSING",
        analysis_protocol="2.4",
        discussion_state={"enabled": True, "mode": "discussion", "revision": 0},
    )
    RequestMessage.objects.create(request=row, role="user", kind="need", content=row.need)
    return row


def detail(client, row):
    response = client.get(f"/api/analyses/{row.pk}")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.parametrize(
    "raw,job_status,waiting,expected,incident",
    [
        ("DISCUSSING", None, "", "DISCUSSION", False),
        ("READY", "DONE", "", "DISCUSSION", False),
        ("PARTIAL", "DONE", "", "DISCUSSION", False),
        ("ANALYZING", "RUNNING", "", "IN_PROGRESS", False),
        ("QUEUED", "QUEUED", "quota_exhausted", "WAITING_AI", False),
        ("NEEDS_CLARIFICATION", "DONE", "", "AWAITING_REPLY", False),
        ("ERROR", "ERROR", "", "DISCUSSION", True),
        ("CANCELLED", "CANCELLED", "", "DISCUSSION", True),
        ("ANALYZING", None, "", "DISCUSSION", True),
        ("DISCUSSING", "ERROR", "", "DISCUSSION", True),
    ],
)
def test_conversation_state_follows_actual_operation(
    client, environment, raw, job_status, waiting, expected, incident
):
    row = conversation(environment)
    row.status = raw
    row.save()
    if job_status:
        Job.objects.create(
            kind="discussion",
            target=str(row.pk),
            status=job_status,
            payload={"waiting_reason": waiting},
            error="Provider failed" if job_status == "ERROR" else "",
        )
    data = detail(client, row)
    assert data["conversation_state"] == expected
    assert data["conversation_incident"] is incident
    if job_status == "ERROR":
        assert data["conversation_error"] == "Provider failed"
    listing = client.get("/api/analyses", {"conversation_status": expected}).json()
    assert str(row.pk) in [item["id"] for item in listing["items"]]
    assert row.status == raw


def test_archive_search_and_reopen_preserve_every_record(client, environment):
    row = conversation(environment)
    RequestMessage.objects.create(
        request=row, role="assistant", kind="discussion_reply", content="UNIQUE_CONTENT_KEY"
    )
    session = AISession.objects.create(request=row, agent="codex", role="d-shared")
    row.primary_session = session
    row.save()
    before = row.updated_at
    cursor = client.get(f"/api/analyses/{row.pk}/progress").json()["progress_cursor"]
    url = f"/api/analyses/{row.pk}/archive"
    assert client.patch(url, {"archived": True}, content_type="application/json").status_code == 200
    row.refresh_from_db()
    assert row.updated_at == before and row.primary_session_id == session.pk
    assert not client.get(f"/api/analyses/{row.pk}/progress", {"cursor":cursor}).json().get("unchanged")
    assert client.get("/api/analyses").json()["total"] == 0
    assert (
        client.get("/api/analyses", {"archived": "archived", "q": "UNIQUE_CONTENT_KEY"}).json()[
            "total"
        ]
        == 1
    )
    assert len(detail(client, row)["messages"]) == 2
    assert (
        client.post(
            f"/api/analyses/{row.pk}/discussion",
            {"expected_revision": 0, "message": "Continue"},
            content_type="application/json",
        ).status_code
        == 409
    )
    assert not Job.objects.exists()
    assert (
        client.patch(url, {"archived": False}, content_type="application/json").status_code == 200
    )
    assert client.get("/api/analyses").json()["total"] == 1


def test_two_cycles_freeze_separate_subjects_git_and_role_sessions(client, environment, storage):
    from core.orchestration import assign_role

    row = conversation(environment)
    first_topic = row.messages.get()
    for number, topic in [(1, first_topic), (2, None)]:
        if topic is None:
            topic = RequestMessage.objects.create(
                request=row, role="user", kind="discussion", content="Explain amount rounding."
            )
            RequestMessage.objects.create(
                request=row, role="assistant", kind="discussion_reply", content="CHAT_HYPOTHESIS"
            )
            environment.repositories.update(sha="b" * 40)
        response = client.post(
            f"/api/analyses/{row.pk}/deep-analyze",
            {
                "expected_revision": 0,
                "subject": topic.content,
                "topic_message_id": topic.pk,
                "message_ids": [topic.pk],
            },
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        run = row.analysis_runs.get(number=number)
        row.refresh_from_db()
        assert run.context_snapshot["dossier"]["need"] == topic.content
        assert [m["id"] for m in run.context_snapshot["dossier"]["user_messages"]] == [topic.pk]
        investigation = context(row, run)
        assert "CHAT_HYPOTHESIS" not in str(investigation)
        if number == 2:
            assert investigation["previous_result"] is None
            assert "OLD_CYCLE_PROOF" not in str(investigation)
        sessions = [
            assign_role(row, run, role) for role in ["analyst", "counter_analyst", "verifier"]
        ]
        assert len({s.context_id for s in sessions}) == 3
        run.refresh_from_db()
        frozen = copy.deepcopy(run.context_snapshot)
        ResultVersion.objects.create(
            request=row,
            run=run,
            number=number,
            status="PARTIAL",
            baseline=row.baseline,
            context_snapshot=frozen,
            explanation={"summary": "OLD_CYCLE_PROOF" if number == 1 else "Rounding explanation"},
        )
        run.status = "PARTIAL"
        run.finished_at = timezone.now()
        run.save()
        Job.objects.filter(pk=run.job_id).update(status="DONE", finished_at=timezone.now())
        row.status = "PARTIAL"
        row.save()
    a, b = row.analysis_runs.order_by("number")
    assert a.context_snapshot["dossier"]["baseline"][0]["sha"] == "a" * 40
    assert b.context_snapshot["dossier"]["baseline"][0]["sha"] == "b" * 40
    assert not set(a.orchestration["sessions"].values()) & set(b.orchestration["sessions"].values())
    assert len(detail(client, row)["versions"]) == 2


def save_draft(client, row, draft, **changes):
    return client.put(
        f"/api/analyses/{row.pk}/ticket-preparation",
        {
            "new_ticket": not bool(draft.get("id")),
            "ticket_id": draft.get("id"),
            "expected_revision": draft["revision"],
            "expected_discussion_revision": draft["discussion_revision"],
            "source_version": draft["source_version"],
            "topic_message_id": draft["topic_message_id"],
            "title": draft["title"],
            "body": draft["body"],
            **changes,
        },
        content_type="application/json",
    )


def test_multiple_tickets_have_explicit_sources_and_independent_edits(client, environment):
    row = conversation(environment)
    topics = [
        row.messages.get(),
        RequestMessage.objects.create(
            request=row, role="user", kind="discussion", content="Explain rounding"
        ),
    ]
    for n, topic in enumerate(topics, 1):
        run = AnalysisRun.objects.create(request=row, number=n, status="PARTIAL")
        ResultVersion.objects.create(
            request=row,
            run=run,
            number=n,
            status="PARTIAL",
            context_snapshot={
                "dossier": {
                    "need": topic.content,
                    "cycle_scope": {"message_ids": [topic.pk], "topic_message_id": topic.pk},
                }
            },
            explanation={"summary": f"FINDING_{n}"},
        )
    endpoint = f"/api/analyses/{row.pk}/ticket-preparation"
    candidate = client.get(endpoint, {"new_ticket": True}).json()
    assert candidate["needs_source_choice"] and candidate["source_version"] is None
    drafts = []
    for n in [1, 2]:
        draft = client.get(endpoint, {"new_ticket": True, "source_version": n}).json()
        assert draft["source_version"] == n
        assert draft["verified_scope"] == topics[n - 1].content
        assert topics[n - 1].content in draft["body"]
        assert f"FINDING_{3 - n}" not in draft["body"]
        response = save_draft(client, row, draft, title=f"Ticket {n}")
        assert response.status_code == 200, response.content
        drafts.append(response.json())
    assert drafts[0]["id"] != drafts[1]["id"]
    edited = save_draft(client, row, drafts[0], body="Dates only")
    assert edited.status_code == 200
    assert client.get(endpoint, {"ticket_id": drafts[1]["id"]}).json()["body"] == drafts[1]["body"]
    assert save_draft(client, row, drafts[0], body="Stale edit").status_code == 409
    assert len(detail(client, row)["conversation_tickets"]) == 2
    listing = client.get("/api/tickets", {"status": "all"}).json()
    assert listing["total"] == 0
    assert client.get(f"/api/tickets/{drafts[0]['id']}").json()["description"] == "Dates only"
    assert not Job.objects.exists()
    other = conversation(environment)
    assert (
        client.get(
            f"/api/analyses/{other.pk}/ticket-preparation", {"ticket_id": drafts[0]["id"]}
        ).status_code
        == 404
    )
    assert ConversationTicket.objects.count() == 2


def test_question_result_remains_readable_after_a_change_cycle(client, environment, storage):
    from core.models import GeneratedArtifact

    row = conversation(environment)
    row.workflow = "question"
    row.save()
    version = ResultVersion.objects.create(
        request=row,
        number=1,
        status="PARTIAL",
        context_snapshot={"dossier": {"need": "Explain dates", "workflow": "question"}},
        explanation={"summary": "Frozen explanation"},
    )
    GeneratedArtifact.objects.create(
        version=version, name="answer.md", content="# Dates explanation"
    )
    topic = row.messages.get()
    response = client.post(
        f"/api/analyses/{row.pk}/deep-analyze",
        {
            "expected_revision": 0,
            "intent": "change",
            "subject": "Prevent invalid dates",
            "message_ids": [topic.pk],
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    previous = client.get(f"/api/questions/{row.pk}/versions/1")
    assert previous.status_code == 200, previous.content
    assert previous.json()["workflow"] == "question"
    assert previous.json()["explanation"]["summary"] == "Frozen explanation"
    assert client.get(f"/api/questions/{row.pk}/versions/1/artifacts/answer.md").status_code == 200
    assert detail(client, row)["versions"][0]["workflow"] == "question"


def test_scoped_subject_can_exclude_all_previous_messages(client, environment, storage):
    row = conversation(environment)
    response = client.post(
        f"/api/analyses/{row.pk}/deep-analyze",
        {
            "expected_revision": 0,
            "subject": "Explain source imports",
            "message_ids": [],
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    snapshot = row.analysis_runs.get().context_snapshot["dossier"]
    assert snapshot["user_messages"] == []
    assert snapshot["cycle_scope"]["topic_message_id"] is None
    assert snapshot["need"] == "Explain source imports"


def test_delayed_generation_updates_only_its_original_ticket(environment):
    from types import SimpleNamespace

    from core.ticket_preparation import complete_generation

    row = conversation(environment)
    topic = row.messages.get()
    first = ConversationTicket.objects.create(
        request=row, draft={"revision": 1, "title": "Dates", "body": "First"}
    )
    second = ConversationTicket.objects.create(
        request=row, draft={"revision": 1, "title": "Rounding", "body": "Keep second"}
    )
    row.discussion_state.update(
        ticket_preparation_id=str(second.pk), ticket_preparation=second.draft
    )
    row.save()
    job = Job.objects.create(
        kind="discussion",
        target=str(row.pk),
        payload={
            "ticket_preparation": {
                "conversation_ticket_id": str(first.pk),
                "expected_draft_revision": 1,
                "source_version": None,
                "scope_choice": "unknown",
                "inputs": {"topic": {"id": topic.pk}, "observations": []},
            }
        },
    )
    assert complete_generation(
        row, job, SimpleNamespace(title="Dates draft", body="Generated dates", sources=[], clarification="")
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.draft["body"] == "Generated dates" and first.draft["revision"] == 2
    assert second.draft["body"] == "Keep second" and second.draft["revision"] == 1


def test_legacy_result_action_excludes_a_later_unrelated_question(client, environment):
    row = conversation(environment)
    original = row.messages.get()
    ResultVersion.objects.create(
        request=row, number=1, status="PARTIAL", explanation={"summary": "Dates findings"}
    )
    RequestMessage.objects.create(
        request=row, role="user", kind="discussion", content="UNRELATED_ROUNDING_QUESTION"
    )
    response = client.get(
        f"/api/analyses/{row.pk}/ticket-preparation", {"new_ticket": True, "source_version": 1}
    )
    assert response.status_code == 200, response.content
    assert response.json()["topic_message_id"] == original.pk
    assert "UNRELATED_ROUNDING_QUESTION" not in response.json()["body"]


def test_result_type_survives_later_intent_changes(client, environment):
    row = conversation(environment)
    row.workflow = "question"
    row.save()
    ResultVersion.objects.create(
        request=row, number=1, status="PARTIAL", explanation={"summary": "Dates"}
    )
    ResultVersion.objects.create(
        request=row,
        number=2,
        status="READY",
        ticket={"title": "Correct dates"},
        context_snapshot={"dossier": {"workflow": "question"}},
    )
    value = detail(client, row)
    assert {v["number"]: v["workflow"] for v in value["versions"]} == {1: "question", 2: "request"}
    assert value["latest_version"]["workflow"] == "request"
    assert client.get(f"/api/requests/{row.pk}").status_code == 200
    row.workflow = "request"
    row.save()
    assert client.get(f"/api/questions/{row.pk}").status_code == 200
