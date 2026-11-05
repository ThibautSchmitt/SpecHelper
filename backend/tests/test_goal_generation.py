import copy
import json
from uuid import uuid4

import pytest

from core import discussion
from core.models import (
    AIConnection,
    AnalysisRun,
    ConversationTicket,
    Job,
    Request,
    RequestMessage,
    ResultVersion,
)
from core.providers import bind_session

pytestmark = pytest.mark.django_db


@pytest.fixture
def thread(environment, storage, monkeypatch):
    value = Request.objects.create(
        environment=environment,
        language="fr",
        need="Historical unrelated question",
        status="DISCUSSING",
        analysis_protocol="2.4",
        discussion_state={"enabled": True, "mode": "discussion", "revision": 1},
    )
    RequestMessage.objects.create(
        request=value,
        role="user",
        kind="discussion",
        content="Implement an explicit synchronization schedule, keeping missing frequency undecided.",
    )
    session = bind_session(value, AIConnection.objects.get(pk=1), "d-shared")
    session.runtime_id = str(uuid4())
    session.save()
    value.discussion_state.update(session_pk=session.pk, connection_id=1)
    value.save()
    monkeypatch.setattr("core.git.request_workspace", lambda value: storage)
    return value


def start(client, value, ticket=None):
    return client.post(
        f"/api/analyses/{value.pk}/goal/generate" + (f"?ticket_id={ticket.pk}" if ticket else ""),
        {},
        content_type="application/json",
    )


def finish(value, check=None, sources=None):
    job = Job.objects.filter(target=str(value.pk), payload__has_key="goal_generation").latest("id")
    job.status = "RUNNING"
    job.save()

    def runtime(path, payload, **kwargs):
        assert payload["persistent_conversation"]
        assert payload["session_id"] == value.ai_sessions.get(role="d-shared").runtime_id
        assert payload["database"] is None
        assert payload["schema"]["title"] == "GoalReply"
        data = json.loads(payload["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
        assert (
            "potential impacts" in payload["prompt"] and "blocking questions" in payload["prompt"]
        )
        if check:
            check(data)
        return {
            "session_id": payload["session_id"],
            "output": {
                "content": "# Objectif\n\nImplémenter la synchronisation décrite dans le ticket.\n\n## Investigations préalables\n\nDéfinir la fréquence avant de choisir un mécanisme de planification.\n\n## Impacts possibles\n\nVérifier la concurrence sans présumer de la solution.\n\n## Périmètre\n\nRespecter le ticket.\n\n## Tests\n\nVérifier la synchronisation.",
                "sources": sources or [],
            },
        }

    discussion.run_job(job, runtime)
    job.refresh_from_db()
    return job


def test_goal_is_a_deduplicated_native_drafting_turn_and_preserves_manual_edits(client, thread):
    ticket = ConversationTicket.objects.create(
        request=thread,
        draft={
            "revision": 2,
            "title": "Synchronisation PostgreSQL",
            "body": "Manual choice: synchronize incrementally. Frequency remains undefined.",
        },
    )
    previous = copy.deepcopy(ticket.draft)
    response = start(client, thread, ticket)
    assert response.status_code == 200, response.content
    queued = response.json()
    assert queued["status"] == "QUEUED"
    duplicate = start(client, thread, ticket)
    assert duplicate.json()["generation_id"] == queued["generation_id"]
    assert Job.objects.count() == 1 and not AnalysisRun.objects.exists()

    def check(data):
        assert data["ticket"] == {"id": str(ticket.pk), **previous}
        assert data["baseline"][0]["sha"] == "a" * 40

    job = finish(thread, check)
    result = client.get(f"/api/analyses/{thread.pk}/goal?generation_id={job.pk}").json()
    assert result["status"] == "DONE" and "Investigations préalables" in result["content"]
    assert "Sans vérification approfondie" in result["content"] and not result["verified"]
    assert "Search Sort Limit" not in result["content"]
    ticket.refresh_from_db()
    assert ticket.draft == previous
    assert not ResultVersion.objects.exists() and not AnalysisRun.objects.exists()
    RequestMessage.objects.create(
        request=thread, role="assistant", kind="session_notice", content="Native session recovered"
    )
    assert start(client, thread, ticket).json()["generation_id"] == job.pk
    ticket.draft = {**previous, "revision": 3, "body": "A new manual correction"}
    ticket.save()
    assert start(client, thread, ticket).json()["generation_id"] != job.pk


def test_unknown_source_cannot_be_claimed_and_draft_changes_are_never_overwritten(client, thread):
    ticket = ConversationTicket.objects.create(
        request=thread,
        draft={
            "revision": 1,
            "title": "Implement synchronization",
            "body": "Manual starting content",
        },
    )
    assert start(client, thread, ticket).status_code == 200
    ticket.draft.update(revision=2, body="Concurrent manual edits")
    ticket.save()
    with pytest.raises(ValueError, match="unknown source"):
        finish(thread, sources=["invented:999"])
    ticket.refresh_from_db()
    assert ticket.draft["body"] == "Concurrent manual edits"
    job = Job.objects.get()
    assert "document" not in job.payload["goal_generation"]


def test_read_only_exports_do_not_queue_ai_and_generation_is_scoped(client, thread):
    before = Job.objects.count()
    client.get(f"/api/analyses/{thread.pk}/goal")
    assert Job.objects.count() == before
    other = Request.objects.create(environment=thread.environment, need="Other")
    foreign = ConversationTicket.objects.create(
        request=other, draft={"title": "Private other topic"}
    )
    assert start(client, thread, foreign).status_code == 404
    assert start(client, thread).status_code == 200
    job = Job.objects.latest("id")
    assert client.get(f"/api/analyses/{other.pk}/goal?generation_id={job.pk}").status_code == 404
    assert Job.objects.filter(kind="analysis").count() == 0


def test_goal_does_not_start_while_another_operation_is_active(client, thread):
    Job.objects.create(kind="analysis", target=str(thread.pk), status="QUEUED")
    assert start(client, thread).status_code == 409
    assert Job.objects.count() == 1


def test_explicit_writer_preserves_conversation_session_and_roles(client, thread):
    current = AIConnection.objects.get(pk=1)
    current.roles = []
    current.save()
    writer = AIConnection.objects.create(
        name="ChatGPT writer",
        agent="codex",
        status="CONNECTED",
        availability="AVAILABLE",
        roles=["analyst"],
    )
    original = dict(thread.discussion_state)
    response = client.post(
        f"/api/analyses/{thread.pk}/goal/generate?connection_id={writer.pk}",
        {},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    job = Job.objects.latest("id")
    session = thread.ai_sessions.get(pk=job.payload["session_pk"])
    assert session.role == "g-goal" and session.connection_id == writer.pk
    thread.refresh_from_db()
    current.refresh_from_db()
    assert current.roles == []
    assert thread.discussion_state["session_pk"] == original["session_pk"]
    assert thread.discussion_state["connection_id"] == original["connection_id"]
    job.status = "RUNNING"
    job.save()

    def native(path, payload, **kwargs):
        assert payload["session_id"] is None
        assert "bounded_saved_context" in payload["prompt"]
        return {
            "session_id": str(uuid4()),
            "output": {
                "content": "# Objectif\n\nPréparer une implémentation ciblée sans modifier la conversation.\n\n## Décisions manquantes\n\nLa fréquence doit être précisée avant de choisir la stratégie technique.\n\n## Périmètre\n\nRespecter le ticket.\n\n## Impacts\n\nVérifier la concurrence.\n\n## Tests\n\nVérifier les critères définis.",
                "sources": [],
            },
        }

    discussion.run_job(job, native)
    thread.refresh_from_db()
    job.refresh_from_db()
    assert job.status == "DONE"
    assert thread.discussion_state["session_pk"] == original["session_pk"]
    assert thread.discussion_state["connection_id"] == original["connection_id"]
    assert not AnalysisRun.objects.exists()


def test_explicit_writer_cannot_bypass_role_authorization(client, thread):
    connection = AIConnection.objects.create(
        name="Not authorized", agent="codex", roles=[], status="CONNECTED"
    )
    response = client.post(
        f"/api/analyses/{thread.pk}/goal/generate?connection_id={connection.pk}",
        {},
        content_type="application/json",
    )
    assert response.status_code == 409 and not Job.objects.exists()


def test_goal_cannot_be_a_file_write_failure_report():
    from pydantic import ValidationError

    from core.goal_generation import GoalReply

    with pytest.raises(ValidationError, match="complete multi-section"):
        GoalReply(
            content="## Synthèse\n\nLe fichier goal.md n’a pas pu être écrit car l’outil d’édition a refusé la création du fichier dans cet espace de travail."
        )
