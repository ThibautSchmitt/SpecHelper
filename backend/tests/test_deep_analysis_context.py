"""Deep launch chooses contextual inputs, never evidence, without a message picker."""

import copy
import json
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core import discussion, environment_context
from core.analysis_flow import context
from core.models import (
    AIConnection,
    AISession,
    AnalysisRun,
    ConversationTicket,
    Job,
    Request,
    RequestMessage,
    ResultVersion,
)
from core.orchestration import assign_role
from core.providers import bind_session

pytestmark = pytest.mark.django_db


@pytest.fixture
def thread(environment, storage, monkeypatch):
    row = Request.objects.create(
        environment=environment,
        need="Explain PostgreSQL synchronization",
        language="en",
        analysis_protocol="2.4",
        status="DISCUSSING",
        discussion_state={"enabled": True, "mode": "discussion", "revision": 1},
    )
    RequestMessage.objects.create(
        request=row,
        role="user",
        kind="discussion",
        content="How does PostgreSQL synchronization work?",
    )
    session = bind_session(row, AIConnection.objects.get(pk=1), "d-shared")
    session.runtime_id = str(uuid4())
    session.save()
    row.discussion_state.update(session_pk=session.pk, connection_id=1)
    row.save()

    def workspace(value):
        path = storage / "workspace" / str(value.pk)
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("core.git.request_workspace", workspace)
    return row


def detail(client, row):
    response = client.get(f"/api/analyses/{row.pk}")
    assert response.status_code == 200, response.content
    return response.json()


def launch(client, row, subject="Investigate implementing PostgreSQL synchronization", **extra):
    value = detail(client, row)
    return client.post(
        f"/api/analyses/{row.pk}/deep-analyze",
        {"expected_revision": value["discussion"]["revision"], "subject": subject, **extra},
        content_type="application/json",
    )


def finish_context(row, output, check=None):
    job = Job.objects.filter(target=str(row.pk), kind="discussion").latest("id")
    job.status = "RUNNING"
    job.save()

    def native(path, payload, **kwargs):
        assert (
            payload["session_id"]
            == (AISession.objects.get(pk=row.discussion_state["session_pk"]).runtime_id or None)
        )
        assert "ContextSelection" in payload["schema"]["title"]
        assert payload["persistent_conversation"]
        if check:
            check(payload)
        return {"session_id": payload["session_id"] or str(uuid4()), "output": output}

    discussion.run_job(job, native)
    job.refresh_from_db()
    return job


def test_native_hint_prefills_a_complete_need_after_yes(client, thread):
    root = thread.messages.get()
    proposal = RequestMessage.objects.create(
        request=thread,
        role="assistant",
        kind="discussion_reply",
        content="Would you implement direct PostgreSQL synchronization?",
    )
    yes = RequestMessage.objects.create(
        request=thread, role="user", kind="discussion", content="Oui."
    )
    RequestMessage.objects.create(
        request=thread,
        role="assistant",
        kind="discussion_reply",
        content="The desired change is clear.",
        data={
            "analysis_context": {
                "need": "Implement direct PostgreSQL synchronization",
                "message_ids": [root.pk, proposal.pk, yes.pk],
            }
        },
    )
    value = detail(client, thread)
    assert value["deep_analysis_need"] == "Implement direct PostgreSQL synchronization"
    assert not Job.objects.exists()
    assert launch(client, thread, "oui").status_code == 422
    assert not Job.objects.exists()


def test_ambiguous_or_foreign_hint_never_prefills_an_old_subject(client, thread, environment):
    RequestMessage.objects.create(request=thread, role="user", kind="discussion", content="Yes")
    assert detail(client, thread)["deep_analysis_need"] == ""
    other = Request.objects.create(environment=environment, need="Other project")
    foreign = RequestMessage.objects.create(
        request=other, role="user", kind="discussion", content="Unrelated"
    )
    RequestMessage.objects.create(
        request=thread,
        role="assistant",
        kind="discussion_reply",
        content="Uncertain",
        data={"analysis_context": {"need": "Invented need", "message_ids": [foreign.pk]}},
    )
    assert detail(client, thread)["deep_analysis_need"] == ""


def test_yes_is_paired_with_its_exchange_and_never_becomes_proof(client, thread):
    root = thread.messages.get()
    question = RequestMessage.objects.create(
        request=thread,
        role="assistant",
        kind="discussion_reply",
        content="UNVERIFIED_ASSUMPTION. Include archived playlists?",
    )
    yes = RequestMessage.objects.create(
        request=thread, role="user", kind="discussion", content="yes"
    )
    response = launch(client, thread)
    assert response.status_code == 200, response.content
    assert not AnalysisRun.objects.exists()
    job = finish_context(thread, {"message_ids": [yes.pk]})
    assert job.status == "DONE"
    run = thread.analysis_runs.get()
    dossier = run.context_snapshot["dossier"]
    assert dossier["need"] == "Investigate implementing PostgreSQL synchronization"
    assert [m["id"] for m in dossier["context_exchanges"]] == [root.pk, question.pk, yes.pk]
    assert dossier["context_exchanges"][-1]["classification"] == "contextual_confirmation"
    assert not any(m["is_technical_evidence"] for m in dossier["context_exchanges"])
    assert not thread.business_decisions.exists()
    assert context(Request.objects.get(pk=thread.pk), run)["conversation_context_is_not_evidence"]
    assert not ConversationTicket.objects.exists()


def test_long_conversation_returns_to_a_prior_need_without_mixing_topics(client, thread):
    root = thread.messages.get()
    clarification = RequestMessage.objects.create(
        request=thread,
        role="user",
        kind="answer",
        content="Exclude archived playlists from synchronization.",
    )
    for number in range(100):
        RequestMessage.objects.create(
            request=thread, role="user", kind="discussion", content=f"UNRELATED_EXPORT_{number}"
        )
        RequestMessage.objects.create(
            request=thread,
            role="assistant",
            kind="discussion_reply",
            content=f"UNRELATED_HYPOTHESIS_{number}",
        )
    RequestMessage.objects.create(
        request=thread,
        role="user",
        kind="discussion",
        content="Return to the PostgreSQL synchronization issue.",
    )
    assert launch(client, thread).status_code == 200
    queued = Job.objects.latest("id")
    assert len(queued.payload["analysis_preparation"]["inputs"]["exchanges"]) <= 56
    finish_context(thread, {"message_ids": [root.pk, clarification.pk]})
    run = thread.analysis_runs.get()
    inputs = context(Request.objects.get(pk=thread.pk), run)
    assert "Exclude archived playlists" in str(inputs)
    assert "UNRELATED_" not in json.dumps(inputs)
    assert not run.context_snapshot["dossier"]["analysis_references"]


def test_launch_freezes_git_documents_and_keeps_three_independent_sessions(
    client, thread, environment
):
    environment_context.upload_resource(
        environment.pk,
        SimpleUploadedFile("sync.md", b"Original sync policy.", "text/plain"),
        environment.context_revision,
    )
    assert launch(client, thread).status_code == 200
    preparation = Job.objects.latest("id")
    frozen = copy.deepcopy(preparation.payload["snapshot"])
    environment.repositories.update(sha="b" * 40)
    environment.refresh_from_db()
    environment_context.upload_resource(
        environment.pk,
        SimpleUploadedFile("new.md", b"Later document.", "text/plain"),
        environment.context_revision,
    )
    finish_context(
        thread, {"message_ids": [thread.messages.filter(kind="discussion", role="user").first().pk]}
    )
    run = thread.analysis_runs.get()
    assert run.context_snapshot["dossier"]["baseline"] == frozen["dossier"]["baseline"]
    assert run.context_snapshot["resources"] == frozen["resources"]
    assert len(run.context_snapshot["resources"]) == 1
    sessions = [
        assign_role(Request.objects.get(pk=thread.pk), run, role)
        for role in ["analyst", "counter_analyst", "verifier"]
    ]
    chat = AISession.objects.get(pk=thread.discussion_state["session_pk"])
    assert len({s.context_id for s in [chat, *sessions]}) == 4
    assert all(not s.runtime_id for s in sessions)


def test_old_analysis_is_only_a_reference_and_does_not_replace_the_current_need(client, thread):
    old = ResultVersion.objects.create(
        request=thread,
        number=1,
        status="READY",
        technical_summary="OLD_CONCLUSION",
        evidence={"claims": []},
    )
    assert launch(client, thread, "Investigate a different correction").status_code == 200
    finish_context(thread, {"message_ids": [], "analysis_versions": [1]})
    run = thread.analysis_runs.get()
    data = context(Request.objects.get(pk=thread.pk), run)
    assert data["need"] == "Investigate a different correction" and data["previous_result"] is None
    assert data["analysis_references"][0]["id"] == str(old.pk)
    assert data["analysis_references"][0]["verification_required"]
    assert "OLD_CONCLUSION" not in str(data)
    assert thread.versions.get(pk=old.pk).technical_summary == "OLD_CONCLUSION"


def test_missing_context_asks_for_a_clarification_without_starting_or_inventing_analysis(
    client, thread
):
    assert launch(client, thread).status_code == 200
    finish_context(
        thread, {"clarification": "Which synchronization target should be investigated?"}
    )
    assert not thread.analysis_runs.exists()
    assert (
        thread.messages.filter(
            content="Which synchronization target should be investigated?"
        ).count()
        == 1
    )
    assert Request.objects.get(pk=thread.pk).status == "DISCUSSING"
    assert not ConversationTicket.objects.exists()


def test_foreign_or_future_references_cannot_enter_an_analysis(client, thread, environment):
    other = Request.objects.create(environment=environment, need="Other environment")
    foreign = RequestMessage.objects.create(
        request=other, role="user", kind="discussion", content="PRIVATE_OTHER_CONTEXT"
    )
    assert launch(client, thread).status_code == 200
    with pytest.raises(ValueError, match="unavailable"):
        finish_context(thread, {"message_ids": [foreign.pk]})
    assert not thread.analysis_runs.exists()


def test_cancellation_before_native_completion_never_starts_the_three_roles(client, thread):
    assert launch(client, thread).status_code == 200
    job = Job.objects.latest("id")
    job.status = "CANCELLED"
    job.save()
    discussion.run_job(
        job, lambda *args, **kwargs: pytest.fail("Cancelled preparation invoked the assistant")
    )
    assert not thread.analysis_runs.exists()


def test_deep_analysis_from_an_older_active_draft_stays_optional_and_preserves_it(client, thread):
    ticket = ConversationTicket.objects.create(
        request=thread,
        draft={
            "title": "Correct PostgreSQL sync",
            "body": "Preserve archived entries.",
            "revision": 3,
            "discussion_revision": 0,
        },
    )
    original = copy.deepcopy(ticket.draft)
    response = launch(client, thread, preparation_revision=3, ticket_id=str(ticket.pk))
    assert response.status_code == 200, response.content
    finish_context(thread, {"message_ids": []})
    ticket.refresh_from_db()
    assert ticket.active and ticket.draft == original and ConversationTicket.objects.count() == 1
    run = thread.analysis_runs.get()
    assert run.context_snapshot["dossier"]["ticket_proposal"]["verification_status"] == "unverified"


def test_double_click_and_repeated_completion_cannot_create_two_cycles(client, thread):
    assert launch(client, thread).status_code == 200
    assert launch(client, thread).status_code == 409
    job = finish_context(thread, {"message_ids": []})
    discussion.run_job(job, lambda *args, **kwargs: pytest.fail("Completed selection ran twice"))
    assert thread.analysis_runs.count() == 1
    assert Job.objects.filter(kind="discussion").count() == 1


def test_explicit_empty_need_or_out_of_scope_need_does_not_spend_a_turn(client, thread):
    assert launch(client, thread, "").status_code == 422
    response = launch(client, thread, "Write a chocolate cake recipe")
    assert response.status_code == 200
    assert not Job.objects.exists()


def test_unavailable_native_session_recovers_only_bounded_context(client, thread):
    from core.agent import ProviderUnavailable

    for index in range(70):
        RequestMessage.objects.create(
            request=thread, role="user", kind="discussion", content=f"OLD_UNRELATED_{index}"
        )
    assert launch(client, thread).status_code == 200
    job = Job.objects.latest("id")
    job.status = "RUNNING"
    job.save()
    calls = []

    def native(path, payload, **kwargs):
        calls.append(payload)
        if len(calls) == 1:
            raise ProviderUnavailable("SESSION_UNAVAILABLE")
        assert payload["session_id"] is None
        data = json.loads(payload["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
        assert data["recovery"]["older_context_may_be_missing"]
        assert len(data["recovery"]["messages"]) <= 56
        assert 'OLD_UNRELATED_0"' not in payload["prompt"]
        return {
            "session_id": str(uuid4()),
            "output": {"clarification": "What change should be checked?"},
        }

    discussion.run_job(job, native)
    assert len(calls) == 2
    assert not thread.analysis_runs.exists()


def test_normal_reply_can_record_a_hint_without_starting_analysis_or_tickets(client, thread):
    response = client.post(
        f"/api/analyses/{thread.pk}/discussion",
        {
            "expected_revision": 1,
            "message": "Investigate a direct PostgreSQL update.",
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    job = Job.objects.latest("id")
    job.status = "RUNNING"
    job.save()
    message = thread.messages.get(pk=job.payload["message_id"])
    discussion.run_job(
        job,
        lambda path, payload, **kwargs: {
            "session_id": payload["session_id"],
            "output": {
                "message": "We can investigate this update.",
                "analysis_context": {
                    "need": "Investigate a direct PostgreSQL update.",
                    "message_ids": [message.pk],
                },
            },
        },
    )
    assert detail(client, thread)["deep_analysis_need"] == "Investigate a direct PostgreSQL update."
    assert not thread.analysis_runs.exists() and not ConversationTicket.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_postgresql_simultaneous_launches_prepare_one_context(client, environment, storage):
    from django.db import connection

    from tests.test_persistent_discussion_postgres import competing

    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    competing(
        client,
        environment,
        [
            (
                "deep-analyze",
                {
                    "expected_revision": 0,
                    "subject": "Investigate direct PostgreSQL synchronization",
                },
            )
        ]
        * 2,
    )
    assert Job.objects.get().payload["analysis_preparation"]
    assert not AnalysisRun.objects.exists()
