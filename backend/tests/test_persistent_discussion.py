"""Conversation turns preserve native sessions without granting verification or publication."""

import json
from uuid import uuid4

import pytest
from django.test import Client

from core import discussion
from core.agent import ProviderUnavailable
from core.analysis_flow import context
from core.discussion import Reply
from core.models import (
    AIConnection,
    AISession,
    AnalysisRun,
    Job,
    Request,
    RequestMessage,
    ResultVersion,
)
from core.providers import mark_failure
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def native(monkeypatch, storage):
    calls = []

    def workspace(value):
        path = storage / "analysis-workspaces" / str(value.pk)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": True}
        assert path == "/run"
        assert Request.objects.get(pk=payload["request_id"]).status == "CONTINUING_CONVERSATION"
        calls.append(payload)
        return {
            "session_id": payload["session_id"] or str(uuid4()),
            "model": payload["model"] or "fixture-model",
            "output": {"message": "A scoped **discussion** reply; not independently verified."},
        }

    monkeypatch.setattr("core.git.request_workspace", workspace)
    monkeypatch.setattr(discussion, "runtime_call", run)
    return calls


def create(client, environment):
    response = client.post(
        "/api/analyses",
        {"environment_id": environment.pk, "need": "Explain the SQL export in this project."},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def launch(client, value):
    response = client.post(f"/api/analyses/{value['id']}/analyze")
    assert response.status_code == 200, response.content
    return response.json()


def turn(client, value, revision, **changes):
    return client.post(
        f"/api/analyses/{value['id']}/discussion",
        {
            "message": "Explain the exception.",
            "expected_revision": revision,
            **changes,
        },
        content_type="application/json",
    )


def finish():
    job = claim_job()
    assert job and job.kind == "discussion"
    perform_job(job)
    job.refresh_from_db()
    assert job.status == "DONE", job.error
    return job


def test_first_turn_uses_one_assistant_without_a_verified_cycle(client, environment, native):
    value = create(client, environment)
    assert value["discussion"]["enabled"] and value["discussion"]["revision"] == 0
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    assert row.status == "DISCUSSING"
    assert not AnalysisRun.objects.exists() and not ResultVersion.objects.exists()
    assert len(native) == 1 and native[0]["session_id"] is None
    assert native[0]["persistent_conversation"]
    assert AISession.objects.count() == 1
    assert row.messages.filter(kind="discussion_reply").get().data["verified"] is False
    assert not row.business_decisions.exists()


def test_followups_and_reopening_resume_same_native_session(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    finish()
    session = AISession.objects.get()
    first_id = session.runtime_id
    reopened = Client()
    reopened.cookies = client.cookies.copy()
    assert reopened.get(f"/api/analyses/{value['id']}").status_code == 200
    assert turn(reopened, value, 1).status_code == 200
    finish()
    session.refresh_from_db()
    assert session.runtime_id == first_id == native[1]["session_id"]
    assert native[1]["context_id"] == native[0]["context_id"]
    assert '"recovery"' not in native[1]["prompt"]
    assert '"frozen_project_context"' not in native[1]["prompt"]
    assert '"recovery"' in native[0]["prompt"]
    assert not AnalysisRun.objects.exists()


def test_missing_native_session_recovers_explicitly_with_saved_history(
    client, environment, native, monkeypatch
):
    value = create(client, environment)
    launch(client, value)
    finish()
    first = AISession.objects.get()
    old_context, old_native = first.context_id, first.runtime_id
    assert turn(client, value, 1, message="Correct the earlier assumption.").status_code == 200
    recoveries = []

    def resume(path, payload=None, **kwargs):
        recoveries.append(payload)
        if payload["session_id"]:
            raise ProviderUnavailable("SESSION_UNAVAILABLE")
        assert "Correct the earlier assumption." in payload["prompt"]
        return {"session_id": str(uuid4()), "output": {"message": "Recovered discussion reply."}}

    monkeypatch.setattr(discussion, "runtime_call", resume)
    finish()
    first.refresh_from_db()
    assert recoveries[0]["session_id"] == old_native
    assert recoveries[1]["session_id"] is None
    assert first.context_id != old_context
    row = Request.objects.get(pk=value["id"])
    assert row.messages.filter(kind="session_notice").count() == 1
    assert row.messages.filter(role="user").count() == 2
    assert row.messages.filter(kind="discussion_reply").count() == 2


def test_provider_session_replacement_is_never_labeled_a_native_resume(
    client, environment, native, monkeypatch
):
    value = create(client, environment)
    launch(client, value)
    finish()
    assert turn(client, value, 1).status_code == 200
    monkeypatch.setattr(
        discussion,
        "runtime_call",
        lambda *a, **k: {
            "session_id": str(uuid4()),
            "output": {"message": "A reply from a changed provider session."},
        },
    )
    finish()
    row = Request.objects.get(pk=value["id"])
    assert row.messages.filter(kind="discussion_reply").latest("id").data["native_resumed"] is False
    assert row.messages.filter(kind="session_notice").count() == 1


def test_provider_error_does_not_fabricate_a_reply_or_loop(
    client, environment, native, monkeypatch
):
    value = create(client, environment)
    launch(client, value)
    attempted = []

    def fail(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": True}
        attempted.append(payload)
        raise ProviderUnavailable("ERROR")

    monkeypatch.setattr(discussion, "runtime_call", fail)
    job = claim_job()
    perform_job(job)
    row = Request.objects.get(pk=value["id"])
    assert row.status == "ERROR" and row.error
    assert row.messages.filter(role="assistant").count() == 0
    assert len(attempted) == 1
    assert AIConnection.objects.get(pk=1).availability == "AVAILABLE"
    assert turn(client, value, 1, restart_session=True, message="").status_code == 200
    assert row.messages.filter(role="user").count() == 1


def test_no_silent_switch_on_quota_or_configuration_change(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    finish()
    chosen = AISession.objects.get().connection
    chosen.model = "new-model"
    chosen.save(update_fields=["model"])
    assert turn(client, value, 1).status_code == 409
    assert RequestMessage.objects.filter(role="user").count() == 1
    assert turn(client, value, 1, restart_session=True).status_code == 200
    finish()
    assert len(set(call["context_id"] for call in native)) == 2
    AIConnection.objects.create(
        name="Alternative",
        agent="claude",
        enabled=True,
        status="CONNECTED",
        availability="AVAILABLE",
    )
    mark_failure(chosen.pk, "QUOTA_EXHAUSTED")
    assert turn(client, value, 2).status_code == 200
    assert claim_job() is None
    assert Job.objects.latest("id").payload["assignment"]["connection_id"] == chosen.pk


def test_browser_owners_and_environments_do_not_share_sessions_or_private_records(
    client, environment, native
):
    value = create(client, environment)
    launch(client, value)
    finish()
    stranger = Client()
    assert stranger.get(f"/api/analyses/{value['id']}").status_code == 404
    assert (
        stranger.post(
            f"/api/analyses/{value['id']}/discussion",
            {"message": "Another user", "expected_revision": 1},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert stranger.get("/api/analyses").json()["total"] == 0
    assert stranger.get("/api/questions").json() == []
    assert stranger.get("/api/queue").json() == []
    second = create(stranger, environment)
    launch(stranger, second)
    finish()
    assert native[0]["context_id"] != native[1]["context_id"]
    assert native[0]["request_id"] != native[1]["request_id"]


def test_deep_analysis_freezes_human_context_and_uses_distinct_role_sessions(
    client, environment, native
):
    from core.orchestration import assign_role

    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    RequestMessage.objects.create(
        request=row, role="assistant", kind="discussion_reply", content="UNVERIFIED_CHAT_HYPOTHESIS"
    )
    chat_session = AISession.objects.get()
    response = client.post(
        f"/api/analyses/{row.pk}/deep-analyze",
        {"expected_revision": 1},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    job = claim_job()
    assert job.kind == "analysis"
    run = AnalysisRun.objects.get(job=job)
    row.refresh_from_db()
    frozen = run.context_snapshot["dossier"]
    assert frozen["discussion_revision"] == 1
    assert all("UNVERIFIED_CHAT_HYPOTHESIS" not in json.dumps(m) for m in frozen["user_messages"])
    assert "UNVERIFIED_CHAT_HYPOTHESIS" not in json.dumps(context(row, run))
    role_sessions = [AISession.objects.get(pk=run.orchestration["sessions"]["analyst"])]
    role_sessions.append(assign_role(row, run, "counter_analyst"))
    role_sessions.append(assign_role(row, run, "verifier"))
    assert len({s.context_id for s in role_sessions} | {chat_session.context_id}) == 4
    assert all(not s.runtime_id for s in role_sessions)
    assert not row.business_decisions.exists()


def test_conversation_after_result_does_not_rewrite_or_rerun_analysis(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    finish()
    original_native = AISession.objects.get().runtime_id
    row = Request.objects.get(pk=value["id"])
    version = ResultVersion.objects.create(
        request=row,
        number=1,
        status="PARTIAL",
        explanation={"title": "Earlier result", "summary": "Frozen explanation"},
    )
    row.discussion_state.update(analyzed_revision=1, mode="analysis")
    row.status = "PARTIAL"
    row.save()
    assert (
        turn(client, value, 1, message="Explain that result in simpler terms.").status_code == 200
    )
    finish()
    version.refresh_from_db()
    assert version.explanation["summary"] == "Frozen explanation"
    assert not AnalysisRun.objects.exists()
    assert not Job.objects.filter(kind="analysis").exists()
    assert native[-1]["session_id"] == original_native


def test_cancelled_turn_cannot_publish_a_late_response(client, environment, native, monkeypatch):
    value = create(client, environment)
    launch(client, value)

    def late(path, payload=None, **kwargs):
        discussion.cancel_jobs(value["id"])
        return {"session_id": str(uuid4()), "output": {"message": "LATE_RESPONSE"}}

    monkeypatch.setattr(discussion, "runtime_call", late)
    job = claim_job()
    perform_job(job)
    row = Request.objects.get(pk=value["id"])
    assert row.status == "CANCELLED"
    assert not row.messages.filter(content="LATE_RESPONSE").exists()
    assert not ResultVersion.objects.exists()


def test_stale_browser_submission_does_not_duplicate_messages(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    assert turn(client, value, 0).status_code == 409
    finish()
    assert turn(client, value, 0).status_code == 409
    assert turn(client, value, 1).status_code == 200
    assert turn(client, value, 1).status_code == 409
    assert RequestMessage.objects.filter(role="user").count() == 2


def test_factual_clarification_does_not_become_a_business_decision(client, environment):
    from core.business_decisions import accept_answers

    value = create(client, environment)
    row = Request.objects.get(pk=value["id"])
    row.questions = [
        {"id": "screen", "question": "Which screen?", "decision_key": "affected-screen"}
    ]
    row.status = "NEEDS_CLARIFICATION"
    row.save()
    rendered, changed = accept_answers(row, {"screen": "The benefit dossier."})
    assert rendered == {"screen": "The benefit dossier."}
    assert not changed and not row.business_decisions.exists()


def test_reply_schema_is_not_a_verified_result_or_publishable_ticket():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Reply.model_validate({"message": "A discussion reply.", "ticket": {}})


def test_uncertain_stop_keeps_lease_until_runtime_acknowledges(
    client, environment, native, monkeypatch
):
    value = create(client, environment)
    launch(client, value)
    job = claim_job()
    leased = job.payload["connection_ids"]
    assert AIConnection.objects.filter(pk__in=leased, availability="BUSY").exists()

    def unavailable(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": False}
        raise ValueError("Transport interrupted")

    monkeypatch.setattr(discussion, "runtime_call", unavailable)
    perform_job(job)
    job.refresh_from_db()
    assert job.status == "CANCELLED" and job.payload["awaiting_stop"]
    assert AIConnection.objects.filter(pk__in=leased, availability="BUSY").exists()
    assert turn(client, value, 1).status_code == 409
    monkeypatch.setattr(discussion, "runtime_call", lambda *a, **k: {"stopped": True})
    discussion.recover_cancellations()
    job.refresh_from_db()
    assert not job.payload["connection_ids"]
    assert not AIConnection.objects.filter(pk__in=leased, availability="BUSY").exists()
    assert turn(client, value, 1, restart_session=True).status_code == 200


def test_discussion_attachments_remain_read_only_and_freeze_during_turn(
    client, environment, native
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    value = create(client, environment)
    launch(client, value)
    endpoint = f"/api/analyses/{value['id']}/attachments"
    assert (
        client.post(
            endpoint, {"file": SimpleUploadedFile("notes.md", b"Project notes")}
        ).status_code
        == 409
    )
    finish()
    response = client.post(endpoint, {"file": SimpleUploadedFile("notes.md", b"Project notes")})
    assert response.status_code == 201, response.content
    attachment = Request.objects.get(pk=value["id"]).attachments.get()
    from pathlib import Path

    assert Path(attachment.path).stat().st_mode & 0o222 == 0


def test_malformed_identifier_is_not_an_internal_error(client):
    assert client.get("/api/analyses/" + "-" * 36).status_code == 404


def test_resource_wait_has_same_state_in_list_detail_and_activity(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    finish()
    chosen = AISession.objects.get().connection
    mark_failure(chosen.pk, "QUOTA_EXHAUSTED")
    assert turn(client, value, 1).status_code == 200
    assert claim_job() is None
    assert client.get(f"/api/analyses/{value['id']}").json()["result_state"] == "waiting_ai"
    assert client.get("/api/analyses").json()["items"][0]["result_state"] == "waiting_ai"
    cards = client.get("/api/queue").json()
    assert len(cards) == 1 and cards[0]["queue_state"] == "WAITING_AI"


def test_linked_evolution_inherits_private_conversation_owner(client, environment):
    value = create(client, environment)
    row = Request.objects.get(pk=value["id"])
    ResultVersion.objects.create(
        request=row, number=1, status="PARTIAL", explanation={"summary": "A scoped result"}
    )
    payload = {
        "source_version": 1,
        "environment_id": environment.pk,
        "need": "Change the SQL export.",
        "include_context": False,
    }
    endpoint = f"/api/questions/{value['id']}/requests"
    stranger = Client()
    assert stranger.post(endpoint, payload, content_type="application/json").status_code == 404
    response = client.post(endpoint, payload, content_type="application/json")
    assert response.status_code == 201, response.content
    child = response.json()
    assert stranger.get(f"/api/analyses/{child['id']}").status_code == 404
    assert client.get(f"/api/analyses/{child['id']}").status_code == 200


@pytest.mark.parametrize("legacy_shared", [False, True])
def test_revising_enabled_need_continues_discussion_without_deep_pipeline(
    client, environment, native, legacy_shared
):
    value = create(client, environment)
    launch(client, value)
    finish()
    native_id = AISession.objects.get().runtime_id
    if legacy_shared:
        row = Request.objects.get(pk=value["id"])
        row.discussion_state.pop("owner")
        row.discussion_state.pop("private")
        row.save(update_fields=["discussion_state"])
    response = client.post(
        f"/api/analyses/{value['id']}/need",
        {
            "need": "Explain the existing CSV export and its exceptions.",
            "operation_id": str(uuid4()),
            "expected_revision": 0,
            "expected_version": None,
            "expected_decision_revision": 0,
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    finish()
    assert not AnalysisRun.objects.exists()
    assert native[-1]["session_id"] == native_id
    assert Request.objects.get(pk=value["id"]).messages.filter(kind="need_revision").count() == 1
