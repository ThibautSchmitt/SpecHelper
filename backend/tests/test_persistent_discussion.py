"""Conversation turns preserve native sessions without granting verification or publication."""

import copy
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


@pytest.mark.parametrize("provider", ["codex", "claude", "antigravity"])
def test_resumed_turn_receives_new_environment_context_without_rewriting_history(client, environment, native, provider):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.environment_context import update_instructions, upload_resource

    AIConnection.objects.filter(pk=1).update(agent=provider)
    value = create(client, environment)
    launch(client, value)
    original = finish()
    original_snapshot = copy.deepcopy(original.payload["snapshot"])
    row = Request.objects.get(pk=value["id"])
    session = AISession.objects.get(request=row)
    native_id = session.runtime_id
    historical = ResultVersion.objects.create(request=row,number=1,baseline=row.baseline,context_snapshot=original_snapshot)
    update_instructions(environment.pk,"The robot now handles supplemental claims.",True,1,[{"url":"https://example.org/new-rule","note":"New reference"}])
    upload_resource(environment.pk,SimpleUploadedFile("new-rule.md",b"# Supplemental claims"),2)
    assert turn(client,value,row.discussion_state["revision"],message="Explain the updated environment documentation.").status_code == 200
    current = finish()
    assert current.payload["snapshot"]["instructions"]["text"] == "The robot now handles supplemental claims."
    assert len(current.payload["snapshot"]["resources"]) == 1
    inputs = json.loads(native[-1]["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
    manifest = inputs["current_environment_context"]
    assert manifest["supersedes_previous_context"] is True
    assert manifest["instructions"]["text"] == "The robot now handles supplemental claims."
    assert manifest["official_references"][0]["url"] == "https://example.org/new-rule"
    assert manifest["documents"][0]["filename"] == "new-rule.md"
    assert manifest["documents"][0]["path"] == "/context/" + native[-1]["context_resources"][0]["path"]
    assert native[-1]["agent"] == provider and native[-1]["session_id"] == native_id
    assert AISession.objects.count() == 1 and not AnalysisRun.objects.exists()
    original.refresh_from_db()
    historical.refresh_from_db()
    assert original.payload["snapshot"] == historical.context_snapshot == original_snapshot
    # An unchanged continuation keeps the compact manifest and the same session.
    row.refresh_from_db()
    assert turn(client,value,row.discussion_state["revision"]).status_code == 200
    finish()
    inputs = json.loads(native[-1]["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
    assert inputs["current_environment_context"]["unchanged"] is True
    assert native[-1]["session_id"] == native_id


def test_next_turn_uses_current_git_and_database_configuration_with_fresh_observation_policy(client, environment, native):
    from core.models import DatabaseConnection
    from core.secrets import encrypt

    value = create(client, environment)
    launch(client, value)
    original = finish()
    frozen = copy.deepcopy(original.payload["snapshot"])
    row = Request.objects.get(pk=value["id"])
    native_id = AISession.objects.get(request=row).runtime_id
    database = DatabaseConnection.objects.create(name="Business reader",host="db-v1.example.test",database="business",username="readonly",secret=encrypt("fixture-db-secret"))
    environment.database = database
    environment.name = "Renamed environment"
    environment.save()
    environment.repositories.update(sha="b"*40,branch="release/current")
    assert turn(client,value,row.discussion_state["revision"]).status_code == 200
    current = finish()
    assert current.payload["snapshot"]["dossier"]["baseline"][0]["sha"] == "b"*40
    assert current.payload["snapshot"]["dossier"]["database"]["id"] == database.pk
    assert native[-1]["database"]["host"] == "db-v1.example.test"
    assert "fixture-db-secret" not in native[-1]["prompt"]
    inputs = json.loads(native[-1]["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
    assert inputs["current_environment_context"]["database"]["requires_current_queries"] is True
    assert inputs["current_environment_context"]["environment"]["name"] == "Renamed environment"
    database.host = "db-v2.example.test"
    database.save()
    row.refresh_from_db()
    assert turn(client,value,row.discussion_state["revision"]).status_code == 200
    finish()
    inputs = json.loads(native[-1]["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
    assert inputs["current_environment_context"]["supersedes_previous_context"] is True
    assert native[-1]["database"]["host"] == "db-v2.example.test" and native[-1]["session_id"] == native_id
    environment.database = None
    environment.save()
    row.refresh_from_db()
    assert turn(client,value,row.discussion_state["revision"]).status_code == 200
    finish()
    assert native[-1]["database"] is None
    inputs = json.loads(native[-1]["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
    assert inputs["current_environment_context"]["database"]["available"] is False
    original.refresh_from_db()
    assert original.payload["snapshot"] == frozen


@pytest.mark.parametrize("remove", [False, True])
def test_disabled_or_removed_documents_leave_the_next_turn_allowlist(client, environment, native, remove):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.environment_context import edit_resource, upload_resource

    upload_resource(environment.pk,SimpleUploadedFile("rules.md",b"# Old rules"),1)
    value = create(client, environment)
    launch(client, value)
    original = finish()
    resource = environment.context_resources.get()
    edit_resource(environment.pk,resource.pk,2,enabled=False,remove=remove)
    row = Request.objects.get(pk=value["id"])
    assert turn(client,value,row.discussion_state["revision"]).status_code == 200
    current = finish()
    assert current.payload["snapshot"]["resources"] == []
    assert native[-1]["context_resources"] == [] and native[-1]["context_dir"] is None
    inputs = json.loads(native[-1]["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
    assert inputs["current_environment_context"]["documents"] == []
    original.refresh_from_db()
    assert len(original.payload["snapshot"]["resources"]) == 1


def test_context_update_during_a_queued_turn_applies_only_to_the_next_turn(client, environment, native):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.environment_context import update_instructions, upload_resource

    upload_resource(environment.pk,SimpleUploadedFile("rules.md",b"# Original rules"),1)
    value = create(client, environment)
    launch(client, value)
    original = Job.objects.get(kind="discussion")
    frozen = copy.deepcopy(original.payload["snapshot"])
    update_instructions(environment.pk,"Updated context",True,2)
    resource = environment.context_resources.get()
    upload_resource(environment.pk,SimpleUploadedFile("rules.md",b"# New version"),3,resource.pk)
    finish()
    assert native[0]["context_resources"][0]["version_id"] == frozen["resources"][0]["version_id"]
    row = Request.objects.get(pk=value["id"])
    assert turn(client,value,row.discussion_state["revision"]).status_code == 200
    current = finish()
    assert current.payload["snapshot"]["instructions"]["text"] == "Updated context"
    assert native[-1]["context_resources"][0]["version_id"] != native[0]["context_resources"][0]["version_id"]
    original.refresh_from_db()
    assert original.payload["snapshot"] == frozen


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


def test_configuration_change_recovers_automatically_without_switching_connection_on_quota(client, environment, native):
    value = create(client, environment)
    launch(client, value)
    finish()
    chosen = AISession.objects.get().connection
    chosen.model = "new-model"
    chosen.save(update_fields=["model"])
    assert turn(client, value, 1).status_code == 200
    assert RequestMessage.objects.filter(role="user").count() == 2
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


@pytest.mark.parametrize("change", ["model", "reasoning_effort", "identity"])
def test_updated_configuration_starts_one_shared_session_with_recorded_history(client, environment, native, change):
    from core.models import AIIdentity

    value = create(client, environment)
    launch(client, value)
    finish()
    original = AISession.objects.get()
    original_runtime = original.runtime_id
    source = original.connection
    if change == "identity":
        source.identity = AIIdentity.objects.create(agent=source.agent, credential_id=uuid4(), status="CONNECTED", availability="AVAILABLE")
    else:
        setattr(source, change, "new-model" if change == "model" else "medium")
    source.save()
    another_browser = Client()
    assert another_browser.get(f"/api/analyses/{value['id']}").status_code == 200
    assert turn(another_browser, value, 1, message="Keep the original question and inspect the exception.").status_code == 200
    # A stale browser cannot create a competing session or duplicate the message.
    assert turn(client, value, 1).status_code == 409
    assert AISession.objects.count() == 2
    finish()
    current = AISession.objects.latest("id")
    assert current.connection_id == original.connection_id
    assert current.context_id != original.context_id
    assert native[1]["session_id"] is None
    assert "recovery" in native[1]["prompt"] and "Keep the original question" in native[1]["prompt"]
    assert current.model_snapshot == source.model
    assert current.reasoning_effort_snapshot == source.reasoning_effort
    assert current.identity_snapshot == source.identity_id
    original.refresh_from_db()
    assert original.runtime_id == original_runtime
    assert RequestMessage.objects.filter(kind="session_notice").count() == 1
    assert turn(client, value, 2).status_code == 200
    finish()
    assert AISession.objects.count() == 2
    assert native[2]["session_id"] == current.runtime_id
    assert Request.objects.get(pk=value["id"]).discussion_state["session_pk"] == current.pk
    assert not AnalysisRun.objects.exists()


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


@pytest.mark.parametrize("change", ["role", "disabled", "deleted", "disconnected"])
def test_unusable_selected_assistant_can_be_replaced_explicitly(client, environment, native, change):
    from core.models import AIIdentity

    value = create(client, environment)
    launch(client, value)
    finish()
    original_session = AISession.objects.get()
    source = original_session.connection
    original_runtime = original_session.runtime_id
    source.name = "Antigravity"
    source.save()
    if change == "deleted":
        source.delete()
    else:
        if change == "role":
            source.roles = []
        elif change == "disabled":
            source.enabled = False
        else:
            source.status = "DISCONNECTED"
        source.save()
    target = AIConnection.objects.create(
        agent="codex", name="ChatGPT", model="target-model", roles=["analyst"],
        status="CONNECTED", availability="AVAILABLE",
        identity=AIIdentity.objects.create(agent="codex", credential_id=uuid4(), status="CONNECTED", availability="AVAILABLE"),
    )
    if change != "disconnected":
        assert turn(client, value, 1).status_code == 409
    assert Job.objects.count() == 1 and RequestMessage.objects.filter(role="user").count() == 1
    detail = client.get(f"/api/analyses/{value['id']}").json()["discussion"]
    assert detail["connection_id"] == source.pk or change == "deleted"
    assert detail["assistant"]["continuation_reason"] == ("analyst_role_removed" if change == "role" else "connection_unavailable")
    if change == "role":
        assert detail["assistant"]["availability"] == "AVAILABLE"  # Authorization is not a quota failure.
    choices = client.get(f"/api/analyses/{value['id']}/discussion/continuation-options").json()
    assert choices["can_continue"]
    choice = next(row for row in choices["options"] if row["connection_id"] == target.pk)
    payload = {"connection_id":target.pk, "configuration_token":choice["configuration_token"], "expected_revision":1}
    response = client.post(f"/api/analyses/{value['id']}/discussion/continue-with", payload, content_type="application/json")
    assert response.status_code == 200, response.content
    assert response.json()["discussion"]["connection_id"] == target.pk
    assert response.json()["discussion"]["assistant"]["continuation_reason"] == ""
    assert Job.objects.count() == 1 and len(native) == 1  # Selecting an assistant does not generate an answer.
    original_session.refresh_from_db()
    assert original_session.runtime_id == original_runtime
    notice = RequestMessage.objects.filter(kind="session_notice").get()
    assert notice.data["native_session_transferred"] is False
    assert turn(client, value, 2).status_code == 200
    finish()
    assert native[-1]["session_id"] is None and native[-1]["model"] == target.model
    assert "recovery" in native[-1]["prompt"]
    assert not AnalysisRun.objects.exists()
    if change != "deleted":
        source.refresh_from_db()
        assert source.roles == ([] if change == "role" else ["analyst", "counter_analyst", "verifier"])


def test_restored_analyst_role_invalidates_transfer_without_changing_session(client, environment, native):
    from core.models import AIIdentity

    value = create(client, environment)
    launch(client, value)
    finish()
    source = AISession.objects.get().connection
    source.roles = []
    source.save()
    target = AIConnection.objects.create(agent="claude", roles=["analyst"], status="CONNECTED", availability="AVAILABLE",
        identity=AIIdentity.objects.create(agent="claude", credential_id=uuid4(), status="CONNECTED", availability="AVAILABLE"))
    choice = client.get(f"/api/analyses/{value['id']}/discussion/continuation-options").json()["options"][0]
    source.roles = ["analyst"]
    source.save()
    response = client.post(f"/api/analyses/{value['id']}/discussion/continue-with", {
        "connection_id":target.pk,"configuration_token":choice["configuration_token"],"expected_revision":1,
    }, content_type="application/json")
    assert response.status_code == 409
    assert AISession.objects.count() == 1 and Job.objects.count() == 1


@pytest.mark.parametrize("operation", ["goal_generation", "ticket_preparation", "analysis_preparation"])
def test_changing_assistant_does_not_replay_failed_drafting_as_a_discussion(client, environment, native, operation):
    from core.models import AIIdentity

    value = create(client, environment)
    launch(client, value)
    finish()
    source = AISession.objects.get().connection
    source.roles = []
    source.save()
    job = Job.objects.latest("id")
    job.status = "ERROR"
    job.payload[operation] = {"inputs": {}}
    job.save()
    target = AIConnection.objects.create(agent="claude", roles=["analyst"], status="CONNECTED", availability="AVAILABLE",
        identity=AIIdentity.objects.create(agent="claude", credential_id=uuid4(), status="CONNECTED", availability="AVAILABLE"))
    choice = client.get(f"/api/analyses/{value['id']}/discussion/continuation-options").json()["options"][0]
    response = client.post(f"/api/analyses/{value['id']}/discussion/continue-with", {
        "connection_id":target.pk,"configuration_token":choice["configuration_token"],"expected_revision":1,
    }, content_type="application/json")
    assert response.status_code == 200, response.content
    assert Job.objects.count() == 1 and len(native) == 1


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
    client, environment, native, monkeypatch
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
    user_message = row.messages.filter(role="user").first()
    monkeypatch.setattr(discussion, "runtime_call", lambda path, payload, **kwargs: {
        "session_id": chat_session.runtime_id,
        "output": {"message_ids": [user_message.pk]},
    })
    finish()
    job = claim_job()
    assert job.kind == "analysis"
    run = AnalysisRun.objects.get(job=job)
    row.refresh_from_db()
    frozen = run.context_snapshot["dossier"]
    assert frozen["discussion_revision"] == 2
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
    current = client.get(f"/api/analyses/{value['id']}").json()
    assert turn(client, current, current["discussion"]["revision"]).status_code == 200
    finish()
    payload = native[-1]
    sandbox_path = "/attachments/" + Path(attachment.path).name
    assert json.dumps(sandbox_path) in payload["prompt"]
    assert str(Path(attachment.path).parent) not in payload["prompt"]
    assert '"name": "notes.md"' in payload["prompt"]
    assert "actual read-only file in the sandbox" in payload["prompt"]


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


@pytest.mark.parametrize("current_reference", ["anchor", "source", "both"])
def test_ticket_can_reference_the_current_explicit_request(client, environment, native, monkeypatch, current_reference):
    from core.models import ConversationTicket, PublishedTicket

    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    previous = row.messages.filter(role="assistant", kind="discussion_reply").latest("id")
    native_id = AISession.objects.get(request=row).runtime_id

    def run(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped": True}
        inputs = json.loads(payload["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
        current_id = inputs["message_id"]
        assert any(item["id"] == current_id for item in inputs["ticket_context"])
        assert f"message:{current_id}" in inputs["ticket_source_ids"]
        assert payload["schema"]["$defs"]["ConversationTicketReply"]["properties"]["sources"]["items"]["enum"] == inputs["ticket_source_ids"]
        assert payload["agent"] == "codex"
        return {"session_id":payload["session_id"],"output":{
            "message":"Draft prepared from the requested change.",
            "ticket":{"anchor_message_id":current_id if current_reference in {"anchor","both"} else previous.pk,
                      "title":"Reject invalid periods", "body":"Reject reversed contract dates.",
                      "sources":[f"message:{current_id if current_reference in {'source','both'} else previous.pk}"]}}}

    monkeypatch.setattr(discussion,"runtime_call",run)
    assert turn(client,value,row.discussion_state["revision"],message="Prépare un ticket : refuser les périodes dont la fin précède le début.").status_code == 200
    job = finish()
    current_id = job.payload["message_id"]
    ticket = ConversationTicket.objects.get(request=row)
    assert ticket.draft["anchor_message_id"] == (current_id if current_reference in {"anchor","both"} else previous.pk)
    assert ticket.draft["sources"] == [f"message:{current_id if current_reference in {'source','both'} else previous.pk}"]
    assert AISession.objects.count() == 1 and AISession.objects.get(request=row).runtime_id == native_id
    assert not AnalysisRun.objects.exists() and not PublishedTicket.objects.exists()


@pytest.mark.parametrize("invalid_reference", ["foreign_anchor", "foreign_source", "invented_source", "future_source"])
def test_invalid_ticket_reference_preserves_manual_draft_and_reports_context_error(client, environment, native, monkeypatch, invalid_reference):
    from core.models import ConversationTicket, PublishedTicket
    from core.ticket_preparation import TicketReferenceError

    value = create(client, environment)
    launch(client, value)
    finish()
    row = Request.objects.get(pk=value["id"])
    original = {"title":"Human correction","body":"Keep this manually written specification.","revision":1,"source_version":None}
    ticket = ConversationTicket.objects.create(request=row,draft=original)
    other = Request.objects.create(environment=environment,need="Other conversation")
    foreign = RequestMessage.objects.create(request=other,role="user",kind="discussion",content="Foreign private need")

    def run(path, payload=None, **kwargs):
        if path == "/runs/cancel":
            return {"stopped":True}
        current_id = json.loads(payload["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])["message_id"]
        future = RequestMessage.objects.create(request=row,role="user",kind="discussion",content="Later message") if invalid_reference == "future_source" else None
        source = f"message:{foreign.pk}" if invalid_reference == "foreign_source" else f"message:{future.pk}" if future else "message:99999999" if invalid_reference == "invented_source" else f"message:{current_id}"
        return {"session_id":payload["session_id"],"output":{"message":"Proposed draft.","ticket":{
            "title":"Invalid proposal","body":"This must never overwrite the draft.",
            "anchor_message_id":foreign.pk if invalid_reference == "foreign_anchor" else current_id,"sources":[source]}}}

    monkeypatch.setattr(discussion,"runtime_call",run)
    assert turn(client,value,row.discussion_state["revision"],message="Actualise le ticket avec cette précision.").status_code == 200
    job = claim_job()
    perform_job(job)
    job.refresh_from_db()
    ticket.refresh_from_db()
    row.refresh_from_db()
    assert job.status == "ERROR" and job.error == row.error == TicketReferenceError.user_message
    assert ticket.draft == original and ticket.active
    assert ConversationTicket.objects.filter(request=row).count() == 1
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
