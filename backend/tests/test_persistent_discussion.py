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


def test_supervisor_restart_recovers_a_completed_jobs_residual_slot(client, environment):
    from core.providers import capacity_reservations, recover_orphaned_leases

    value = create(client, environment)
    launch(client, value)
    job = claim_job()
    assert len(capacity_reservations()) == 1
    # Simulate interruption after the terminal commit, before the supervisor cleanup.
    Job.objects.filter(pk=job.pk).update(status="DONE")
    recover_orphaned_leases()
    job.refresh_from_db()
    assert not job.payload["connection_ids"] and not job.payload["capacity_reserved"]
    assert not capacity_reservations()


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


def test_recovery_preserves_valid_history_and_excludes_a_confirmed_stale_response(environment):
    row = Request.objects.create(environment=environment, need="An initial question.")
    valid = RequestMessage.objects.create(request=row, role="assistant", kind="discussion_reply", content="A valid earlier response.")
    invalid = RequestMessage.objects.create(request=row, role="assistant", kind="discussion_reply", content="CACHED_STALE_REPLY", data={"response_status":"stale"})
    latest = RequestMessage.objects.create(request=row, role="user", kind="discussion", content="A different question.")
    recovered = discussion.recovery_messages(row, latest.pk)
    assert "CACHED_STALE_REPLY" not in json.dumps(recovered)
    assert valid.content in json.dumps(recovered) and latest.content in json.dumps(recovered)
    assert row.messages.get(pk=invalid.pk).content == "CACHED_STALE_REPLY"


def test_stale_cli_response_is_an_error_without_replaying_or_replacing_the_session(
    client, environment, native, monkeypatch
):
    value = create(client, environment)
    launch(client, value)
    finish()
    session = AISession.objects.get()
    original_context, original_native = session.context_id, session.runtime_id
    assert turn(client, value, 1, message="Explain a different component.").status_code == 200

    def stale(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": True}
        assert payload["session_id"] == original_native
        raise ProviderUnavailable("STALE_RESPONSE")

    monkeypatch.setattr(discussion, "runtime_call", stale)
    job = claim_job()
    perform_job(job)
    job.refresh_from_db()
    row = Request.objects.get(pk=value["id"])
    session.refresh_from_db()
    assert job.status == row.status == "ERROR"
    assert "without completing this turn" in row.error
    assert row.messages.filter(kind="discussion_reply").count() == 1
    assert row.messages.filter(role="user").count() == 2
    assert session.context_id == original_context and session.runtime_id == original_native
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


def test_browsers_share_conversations_and_activity_but_distinct_requests_keep_sessions(
    client, environment, native
):
    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    # Existing browser-private rows become visible without rewriting stored data.
    row.discussion_state["private"] = True
    row.save(update_fields=["discussion_state"])
    stranger = Client()
    detail = stranger.get(f"/api/analyses/{value['id']}")
    assert detail.status_code == 200
    assert stranger.get("/api/analyses").json()["total"] == 1
    assert len(stranger.get("/api/questions").json()) == 1
    assert stranger.get("/api/analyses/overview").json()["recent"][0]["id"] == value["id"]
    response = turn(stranger, value, 1, message="A follow-up from another browser")
    assert response.status_code == 200, response.content
    assert client.get("/api/queue").json() == stranger.get("/api/queue").json()
    assert len(stranger.get("/api/queue").json()) == 1
    # A stale browser cannot append another turn while one is active.
    assert turn(client, value, 1).status_code == 409
    finish()
    assert native[0]["session_id"] is None
    assert native[1]["session_id"] == AISession.objects.get(request=row).runtime_id
    assert native[0]["context_id"] == native[1]["context_id"]
    assert turn(client, value, 2).status_code == 200
    finish()
    assert native[2]["session_id"] == native[1]["session_id"]
    second = create(stranger, environment)
    launch(stranger, second)
    finish()
    assert native[0]["context_id"] != native[3]["context_id"]
    assert native[0]["request_id"] != native[3]["request_id"]


def test_historical_browser_session_is_resumed_after_cookie_change(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    row.discussion_state.pop("session_pk")
    row.discussion_state["private"] = True
    row.save(update_fields=["discussion_state"])
    browser = Client()
    assert turn(browser, value, 1).status_code == 200
    finish()
    assert native[0]["context_id"] == native[1]["context_id"]
    assert AISession.objects.filter(request=row).count() == 1


@pytest.mark.parametrize("provider", ["antigravity", "codex"])
@pytest.mark.parametrize("answered", [False, True])
def test_explicit_quota_transfer_preserves_pending_turn_and_uses_fresh_session(
    client, environment, native, provider, answered
):
    from core.models import AIIdentity

    source = AIConnection.objects.get(pk=1)
    source.name, source.model, source.reasoning_effort = "Original ChatGPT", "original-model", "low"
    source.save()
    value = create(client, environment)
    launch(client, value)
    if answered:
        finish()
        assert turn(client, value, 1, message="Please inspect the exception too.").status_code == 200
    old_job = Job.objects.latest("id")
    original_session = AISession.objects.get(pk=old_job.payload["session_pk"])
    revision = Request.objects.get(pk=value["id"]).discussion_state["revision"]
    mark_failure(source.pk, "QUOTA_EXHAUSTED")
    identity = AIIdentity.objects.create(agent=provider, credential_id=uuid4(),
        status="CONNECTED", availability="AVAILABLE", account_key="another-account")
    target = AIConnection.objects.create(name="Available alternative", agent=provider,
        identity=identity, model="target-model", reasoning_effort="ultra" if provider == "codex" else "",
        status="CONNECTED", availability="AVAILABLE", roles=["analyst"])
    before_messages = list(RequestMessage.objects.filter(request_id=value["id"], role="user").values_list("content", flat=True))
    assert claim_job() is None  # Availability never silently reassigns a discussion.
    detail = client.get(f"/api/analyses/{value['id']}").json()
    assert detail["discussion"]["assistant"]["model"] == "original-model"
    assert detail["discussion"]["assistant"]["reasoning_effort"] == "low"
    assert detail["discussion"]["assistant"]["status"] == "CONNECTED"
    assert detail["discussion"]["assistant"]["enabled"] is True
    assert "quota_windows" in detail["discussion"]["assistant"]
    choices = client.get(f"/api/analyses/{value['id']}/discussion/continuation-options").json()
    choice = next(item for item in choices["options"] if item["connection_id"] == target.pk)
    response = client.post(f"/api/analyses/{value['id']}/discussion/continue-with",
        {"connection_id": target.pk, "configuration_token": choice["configuration_token"], "expected_revision": revision},
        content_type="application/json")
    assert response.status_code == 200, response.content
    assert response.json()["discussion"]["assistant"]["model"] == target.model
    history = response.json()["discussion"]["assistant_history"]
    assert [(item["model"],item["reasoning_effort"],item["current"]) for item in history] == [
        ("original-model","low",False),(target.model,target.reasoning_effort,True),
    ]
    old_job.refresh_from_db()
    assert old_job.status == "CANCELLED"
    new_job = Job.objects.latest("id")
    assert new_job.payload["snapshot"] == old_job.payload["snapshot"]
    assert new_job.payload["message_id"] == old_job.payload["message_id"]
    fresh = AISession.objects.get(pk=new_job.payload["session_pk"])
    assert fresh.context_id != original_session.context_id and not fresh.runtime_id
    assert list(RequestMessage.objects.filter(request_id=value["id"], role="user").values_list("content", flat=True)) == before_messages
    assert RequestMessage.objects.filter(request_id=value["id"], kind="session_notice", data__native_session_transferred=False).count() == 1
    finish()
    assert native[-1]["session_id"] is None
    assert native[-1]["model"] == target.model
    assert native[-1]["reasoning_effort"] == target.reasoning_effort
    assert "recovery" in native[-1]["prompt"] and "unverified" in native[-1]["prompt"]
    assert not AnalysisRun.objects.exists()
    # A stale second browser cannot repeat the transfer.
    duplicate = client.post(f"/api/analyses/{value['id']}/discussion/continue-with",
        {"connection_id": target.pk, "configuration_token": choice["configuration_token"], "expected_revision": revision}, content_type="application/json")
    assert duplicate.status_code == 409


@pytest.mark.parametrize("change", ["quota", "model", "reasoning", "role", "running"])
def test_quota_transfer_revalidates_choice_and_never_interrupts_running_work(client, environment, native, change):
    from core.models import AIIdentity

    value = create(client, environment)
    launch(client, value)
    mark_failure(1, "QUOTA_EXHAUSTED")
    identity = AIIdentity.objects.create(agent="codex", credential_id=uuid4(), status="CONNECTED", availability="AVAILABLE")
    target = AIConnection.objects.create(name="Second account", agent="codex", identity=identity,
        model="another-model", reasoning_effort="low", roles=["analyst"], status="CONNECTED", availability="AVAILABLE")
    options = client.get(f"/api/analyses/{value['id']}/discussion/continuation-options").json()
    choice = next(item for item in options["options"] if item["connection_id"] == target.pk)
    original_job = Job.objects.latest("id")
    if change == "quota":
        mark_failure(target.pk, "QUOTA_EXHAUSTED")
    elif change == "model":
        target.model = "changed-model"
        target.save()
    elif change == "reasoning":
        target.reasoning_effort = "ultra"
        target.save()
    elif change == "role":
        target.roles = ["verifier"]
        target.save()
    else:
        original_job.status = "RUNNING"
        original_job.save()
    response = client.post(f"/api/analyses/{value['id']}/discussion/continue-with",
        {"connection_id": target.pk, "configuration_token": choice["configuration_token"], "expected_revision": 1}, content_type="application/json")
    assert response.status_code == 409, response.content
    original_job.refresh_from_db()
    assert original_job.status == ("RUNNING" if change == "running" else "QUEUED")
    assert AISession.objects.count() == 1


def test_header_preserves_recorded_model_and_effort_after_settings_change(client, environment, native):
    source = AIConnection.objects.get(pk=1)
    source.model, source.reasoning_effort = "recorded-model", "low"
    source.save()
    value = create(client, environment)
    launch(client, value)
    finish()
    source.model, source.reasoning_effort = "new-settings-model", "ultra"
    source.save()
    data = client.get(f"/api/analyses/{value['id']}").json()["discussion"]["assistant"]
    assert data["model"] == "recorded-model" and data["reasoning_effort"] == "low"


def test_completed_discussion_can_select_new_session_without_repeating_an_answer(client, environment, native):
    from core.models import AIIdentity

    value = create(client, environment)
    launch(client, value)
    finish()
    mark_failure(1, "QUOTA_EXHAUSTED")
    target = AIConnection.objects.create(agent="claude", name="Claude", status="CONNECTED", availability="AVAILABLE",
        identity=AIIdentity.objects.create(agent="claude", credential_id=uuid4(), status="CONNECTED", availability="AVAILABLE"))
    choice = client.get(f"/api/analyses/{value['id']}/discussion/continuation-options").json()["options"][0]
    response = client.post(f"/api/analyses/{value['id']}/discussion/continue-with", {
        "connection_id":target.pk,"configuration_token":choice["configuration_token"],"expected_revision":1,
    }, content_type="application/json")
    assert response.status_code == 200, response.content
    assert Job.objects.count() == 1 and len(native) == 1
    assert response.json()["status"] == "DISCUSSING"
    assert turn(client, value, 2).status_code == 200
    finish()
    assert native[-1]["session_id"] is None and native[-1]["agent"] == "claude"


def test_wrapped_reply_is_saved_and_exposed_as_text_without_mutating_old_records(client, environment, native, monkeypatch):
    value = create(client, environment)
    launch(client, value)
    envelope = json.dumps({"message":"Bonjour ! Le message est bien reçu."},ensure_ascii=False)
    monkeypatch.setattr(discussion,"runtime_call",lambda *args,**kwargs:{"session_id":str(uuid4()),"output":{"message":envelope}})
    finish()
    message = RequestMessage.objects.filter(request_id=value["id"],kind="discussion_reply").get()
    assert message.content == "Bonjour ! Le message est bien reçu."
    message.content = envelope  # A reply stored before this correction.
    message.save(update_fields=["content"])
    detail = client.get(f"/api/analyses/{value['id']}").json()
    assert next(row for row in detail["messages"] if row["id"] == message.pk)["content"] == "Bonjour ! Le message est bien reçu."
    message.refresh_from_db()
    assert message.content == envelope


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


def test_linked_evolution_is_shared_across_authorized_browsers(client, environment):
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
    response = client.post(endpoint, payload, content_type="application/json")
    assert response.status_code == 201, response.content
    child = response.json()
    assert stranger.get(f"/api/analyses/{child['id']}").status_code == 200
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


def test_natural_ticket_request_creates_a_scoped_draft_without_deep_analysis(
    client, environment, native, monkeypatch
):
    from core.models import ConversationTicket, PublishedTicket

    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    anchor = row.messages.filter(role="assistant", kind="discussion_reply").latest("id")

    def run(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": True}
        assert "ticket_context" in payload["prompt"]
        return {
            "session_id": payload["session_id"] or str(uuid4()),
            "output": {
                "message": "Draft prepared.",
                "ticket": {
                    "anchor_message_id": anchor.pk,
                    "title": "Reject invalid periods",
                    "body": "## Need\n\nReject an invalid date interval.\n\n## Acceptance criteria\n\n- The record is not saved.",
                    "sources": [f"message:{anchor.pk}"],
                },
            },
        }

    monkeypatch.setattr(discussion, "runtime_call", run)
    response = turn(
        client,
        value,
        row.discussion_state["revision"],
        message="Prépare un ticket pour corriger cette anomalie.",
    )
    assert response.status_code == 200, response.content
    finish()
    ticket = ConversationTicket.objects.get(request=row)
    assert ticket.draft["anchor_message_id"] == anchor.pk
    assert ticket.draft["sources"] == [f"message:{anchor.pk}"]
    assert ticket.source_version_id is None
    assert not AnalysisRun.objects.exists() and not PublishedTicket.objects.exists()


def test_ambiguous_ticket_request_asks_one_question_and_waits_for_its_answer(
    client, environment, native, monkeypatch
):
    from core.models import ConversationTicket

    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    anchor = row.messages.filter(role="assistant", kind="discussion_reply").latest("id")
    asked = []

    def run(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": True}
        if not asked:
            asked.append(True)
            output = {"message": "Which behavior should change?", "ticket_clarification": True}
        else:
            assert "pending_ticket_clarification" in payload["prompt"]
            output = {
                "message": "Draft prepared.",
                "ticket": {
                    "anchor_message_id": anchor.pk,
                    "title": "Validate dates",
                    "body": "Reject an invalid interval.",
                    "sources": [f"message:{anchor.pk}"],
                },
            }
        return {"session_id": payload["session_id"] or str(uuid4()), "output": output}

    monkeypatch.setattr(discussion, "runtime_call", run)
    assert (
        turn(
            client,
            value,
            row.discussion_state["revision"],
            message="Crée un ticket pour le deuxième problème.",
        ).status_code
        == 200
    )
    finish()
    row.refresh_from_db()
    assert row.messages.filter(content="Which behavior should change?").count() == 1
    assert not ConversationTicket.objects.exists()
    assert row.discussion_state.get("pending_ticket_clarification")
    assert (
        turn(
            client,
            value,
            row.discussion_state["revision"],
            message="Il faut refuser les périodes invalides.",
        ).status_code
        == 200
    )
    finish()
    row.refresh_from_db()
    assert ConversationTicket.objects.filter(request=row).count() == 1
    assert (
        not row.discussion_state.get("pending_ticket_clarification")
        and not AnalysisRun.objects.exists()
    )
