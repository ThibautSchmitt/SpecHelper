"""Preparing a draft never launches verification or upgrades its conclusions."""

import copy

import pytest
from django.utils import timezone

from core.analysis_flow import context
from core.models import AISession, AnalysisRun, Job, Request, RequestMessage, ResultVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def analysis(environment):
    value = Request.objects.create(
        environment=environment, need="Explain inconsistent contract dates.", workflow="question",
        analysis_protocol="2.4", language="en", status="DISCUSSING",
        discussion_state={"enabled": True, "mode": "discussion", "revision": 1},
    )
    RequestMessage.objects.create(request=value, role="user", kind="need", content=value.need)
    return value


def endpoint(value):
    return f"/api/analyses/{value.pk}/ticket-preparation"


def save(client, value, draft, **changes):
    return client.put(endpoint(value), {
        "expected_revision": draft["revision"], "expected_discussion_revision": draft["discussion_revision"],
        "source_version": draft["source_version"], "title": draft["title"], "body": draft["body"],
        "scope_choice": draft["scope_choice"], **changes,
    }, content_type="application/json")


def result(value, status="READY"):
    run = AnalysisRun.objects.create(request=value, number=1, status=status, steps=[
        {"public_role": role, "status": "DONE"} for role in ("analyst", "counter_analyst", "verifier")
    ])
    return ResultVersion.objects.create(
        request=value, run=run, number=1, status=status,
        context_snapshot={"dossier": {"need": "Find the cause of inconsistent dates."}},
        explanation={"title": "Contract dates", "summary": "Independent operations can change dates."},
        evidence={"claims": [{"material": True, "status": "supported"}], "blocking": status != "READY",
                  "limitations": ["Runtime checks remain unverified."] if status != "READY" else []},
    )


def test_first_draft_opens_saves_and_reopens_without_analysis(client, analysis):
    response = client.get(endpoint(analysis))
    assert response.status_code == 200, response.content
    draft = response.json()
    assert draft["analysis_state"] == "none" and not draft["source_verified"]
    assert draft["publication_available"]
    response = save(client, analysis, draft, title="Prevent invalid periods", body="Show an error.")
    assert response.status_code == 200, response.content
    assert response.json()["revision"] == 1
    reopened = client.get(endpoint(analysis)).json()
    assert reopened["body"] == "Show an error."
    assert reopened["markdown"] == reopened["body"] and not reopened["ticket_verified"]
    analysis.refresh_from_db()
    assert analysis.workflow == "question" and analysis.status == "DISCUSSING"
    assert analysis.discussion_state["revision"] == 1
    assert not Job.objects.exists() and not AnalysisRun.objects.exists() and not AISession.objects.exists()


def test_existing_analysis_reused_but_later_correction_stays_unverified(client, analysis):
    version = result(analysis)
    frozen = copy.deepcopy(version.context_snapshot)
    RequestMessage.objects.create(request=analysis, role="user", kind="discussion", content="Prevent invalid periods and show an error.")
    RequestMessage.objects.create(request=analysis, role="assistant", kind="discussion_reply", content="UNVERIFIED_ASSISTANT_HYPOTHESIS")
    draft = client.get(endpoint(analysis)).json()
    assert draft["source_version"] == 1 and draft["source_verified"]
    assert draft["has_new_messages"] and draft["verified_scope"] == "Find the cause of inconsistent dates."
    assert "Prevent invalid periods" in draft["body"]
    assert "UNVERIFIED_ASSISTANT_HYPOTHESIS" not in draft["body"]
    assert draft["discussion_findings_available"]
    response = save(client, analysis, draft, scope_choice="clarified")
    assert response.status_code == 200
    assert not response.json()["ticket_verified"]
    version.refresh_from_db()
    assert version.context_snapshot == frozen and version.evidence["claims"][0]["status"] == "supported"
    assert AnalysisRun.objects.count() == 1 and not Job.objects.exists()
    assert not analysis.business_decisions.exists()


@pytest.mark.parametrize("status", ["ERROR", "CANCELLED", "PARTIAL"])
def test_incomplete_or_interrupted_analysis_allows_draft(client, analysis, status):
    if status == "PARTIAL":
        result(analysis, status)
    else:
        AnalysisRun.objects.create(request=analysis, number=1, status=status)
    draft = client.get(endpoint(analysis)).json()
    assert not draft["source_verified"] and draft["publication_allowed"]
    response = save(client, analysis, draft)
    assert response.status_code == 200
    assert not response.json()["ticket_verified"]
    assert not Job.objects.exists()


def test_conflicting_saves_and_new_conversation_inputs_require_reload(client, analysis):
    draft = client.get(endpoint(analysis)).json()
    assert save(client, analysis, draft).status_code == 200
    assert save(client, analysis, draft, body="Overwrite another browser").status_code == 409
    fresh = client.get(endpoint(analysis)).json()
    analysis.discussion_state.update(revision=2)
    analysis.save()
    assert save(client, analysis, fresh, body="Overwrite newer conversation").status_code == 409


def test_other_analysis_versions_and_deleted_conversations_are_not_available(client, analysis, environment):
    other = Request.objects.create(environment=environment, need="Unrelated need")
    ResultVersion.objects.create(request=other, number=9)
    draft = client.get(endpoint(analysis)).json()
    assert save(client, analysis, draft, source_version=9).status_code == 404
    analysis.deleted_at = timezone.now()
    analysis.save()
    assert client.get(endpoint(analysis)).status_code == 404
    assert save(client, analysis, draft).status_code == 404


def test_only_explicit_update_freezes_edited_draft_as_unverified_input(client, analysis):
    draft = client.get(endpoint(analysis)).json()
    saved = save(client, analysis, draft, body="Prevent invalid contract dates with an error.").json()
    assert not Job.objects.exists()
    response = client.post(f"/api/analyses/{analysis.pk}/deep-analyze", {
        "expected_revision": 1, "intent": "change", "preparation_revision": saved["revision"],
    }, content_type="application/json")
    assert response.status_code == 200, response.content
    run = AnalysisRun.objects.get()
    proposal = run.context_snapshot["dossier"]["ticket_proposal"]
    assert proposal["verification_status"] == "unverified" and proposal["revision"] == 1
    assert proposal["body"] == "Prevent invalid contract dates with an error."
    analysis.refresh_from_db()
    inputs = context(analysis, run)
    assert "Prevent invalid contract dates" in inputs["need"]
    assert "body" not in inputs["ticket_proposal"]
    assert "unverified inputs" in inputs["latest_user_message"]
    assert not inputs["confirmed_decisions"] and not AISession.objects.exists()
    # Editing the draft later cannot change the frozen analysis context.
    assert save(client, analysis, saved, body="A later proposal.").status_code == 200
    run.refresh_from_db()
    assert run.context_snapshot["dossier"]["ticket_proposal"] == proposal
    assert Job.objects.filter(kind="analysis").count() == 1
    RequestMessage.objects.create(request=analysis, role="user", kind="clarification", content="Only active contracts are affected.")
    assert context(analysis, run)["latest_user_message"] == "Only active contracts are affected."


def test_stale_draft_revision_cannot_start_analysis(client, analysis):
    draft = client.get(endpoint(analysis)).json()
    saved = save(client, analysis, draft).json()
    assert save(client, analysis, saved, body="A revised draft.").status_code == 200
    response = client.post(f"/api/analyses/{analysis.pk}/deep-analyze", {
        "expected_revision": 1, "preparation_revision": saved["revision"],
    }, content_type="application/json")
    assert response.status_code == 409 and not Job.objects.exists()


def test_latest_subject_reuses_code_answers_without_merging_separate_questions(client, analysis):
    earlier = RequestMessage.objects.create(request=analysis, role="user", kind="answer", content="Clarification question\nExplain import batches.", data={"answers": {"a": "Explain import batches."}})
    RequestMessage.objects.create(request=analysis, role="assistant", kind="discussion_reply", content="BATCH_ONLY_FINDING")
    latest = RequestMessage.objects.create(request=analysis, role="user", kind="discussion", content="Explain the switch menu.")
    RequestMessage.objects.create(request=analysis, role="assistant", kind="discussion_reply", content="STALE_BATCH_REPLY", data={"response_status": "stale"})
    RequestMessage.objects.create(request=analysis, role="assistant", kind="discussion_reply", content="SWITCH_FINDING with source `menu.py:14`.")
    draft = client.get(endpoint(analysis)).json()
    assert draft["title"] == latest.content and draft["topic_message_id"] == latest.pk
    assert draft["discussion_findings_available"]
    assert "SWITCH_FINDING" not in draft["body"] and "menu.py:14" not in draft["body"]
    assert "BATCH_ONLY" not in draft["body"] and "STALE_BATCH" not in draft["body"]
    assert "Clarification question" not in str(draft["topics"])
    selected = client.get(endpoint(analysis), {"topic_message_id": earlier.pk}).json()
    assert selected["discussion_findings_available"] and "SWITCH_FINDING" not in selected["body"]
    assert selected["title"] == "Explain import batches."
    assert not Job.objects.exists()


def test_interrupted_run_public_findings_are_available_without_a_result(client, analysis):
    AnalysisRun.objects.create(request=analysis, number=1, started_at=timezone.now(), status="ERROR", orchestration={"outputs": {
        "analyst": {"claims": [{"statement": "An import validates the file format.", "sources": []}], "private_reasoning": "NEVER_EXPOSE"},
    }})
    draft = client.get(endpoint(analysis)).json()
    assert draft["discussion_findings_available"]
    assert "An import validates" not in draft["body"]
    assert "NEVER_EXPOSE" not in draft["body"] and not draft["source_verified"]


def enqueue_draft(client, analysis):
    draft = client.get(endpoint(analysis)).json()
    return client.post(endpoint(analysis) + "/generate", {
        "expected_revision": draft["revision"], "expected_discussion_revision": draft["discussion_revision"],
        "source_version": draft["source_version"], "topic_message_id": draft["topic_message_id"],
    }, content_type="application/json")


@pytest.fixture
def drafting_runtime(monkeypatch, storage):
    def workspace(value):
        path = storage / "workspaces" / str(value.pk)
        path.mkdir(parents=True, exist_ok=True)
        return path
    monkeypatch.setattr("core.git.request_workspace", workspace)


def test_single_assistant_drafts_from_scoped_sources_and_resumes_its_session(client, analysis, drafting_runtime):
    import json
    from uuid import uuid4

    from core.discussion import run_job
    from core.models import AIConnection
    from core.providers import bind_session

    question = analysis.messages.get(role="user")
    reply = RequestMessage.objects.create(request=analysis, role="assistant", kind="discussion_reply", content="The date check is absent in `contracts.py:42`.")
    existing_session = bind_session(analysis, AIConnection.objects.get(pk=1), "d-shared")
    existing_session.runtime_id = str(uuid4())
    existing_session.save()
    analysis.discussion_state.update(session_pk=existing_session.pk, connection_id=1)
    analysis.save()
    response = enqueue_draft(client, analysis)
    assert response.status_code == 200, response.content
    job = Job.objects.get()
    assert job.kind == "discussion" and not AnalysisRun.objects.exists()
    assert job.payload["ticket_preparation"]["inputs"]["topic"]["id"] == question.pk
    job.status = "RUNNING"
    job.save()
    def runtime(path, payload, **kwargs):
        assert payload["session_id"] == existing_session.runtime_id
        assert "Draft a useful" in payload["prompt"]
        inputs = json.loads(payload["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
        assert "contracts.py:42" in str(inputs["observations"])
        assert "title" in payload["schema"]["properties"]
        return {"session_id": payload["session_id"], "output": {"title": "Investigate inconsistent contract dates", "body": "## Findings\nThe recorded discussion found a missing date check (`contracts.py:42`). Independent verification is incomplete.", "sources": [f"message:{reply.pk}"]}}
    run_job(job, runtime)
    job.refresh_from_db()
    analysis.refresh_from_db()
    assert job.status == "DONE"
    draft = client.get(endpoint(analysis)).json()
    assert draft["title"] == "Investigate inconsistent contract dates"
    assert "contracts.py:42" in draft["body"] and not draft["source_verified"]
    assert not analysis.business_decisions.exists() and not ResultVersion.objects.exists()
    assert AISession.objects.count() == 1
    assert analysis.discussion_state["ticket_preparation"]["sources"] == [f"message:{reply.pk}"]
    from core.ticket_preparation import topic_context

    assert [row.pk for row in topic_context(analysis, question.pk)[1]] == [reply.pk]


def test_generation_cannot_overwrite_concurrent_manual_edits(client, analysis, drafting_runtime):
    from uuid import uuid4

    from core.discussion import run_job

    assert enqueue_draft(client, analysis).status_code == 200
    job = Job.objects.get()
    job.status = "RUNNING"
    job.save()
    def runtime(path, payload, **kwargs):
        current = client.get(endpoint(analysis)).json()
        assert save(client, analysis, current, body="Keep my manual edits").status_code == 200
        return {"session_id": str(uuid4()), "output": {"title": "Generated title", "body": "A generated body", "sources": []}}
    run_job(job, runtime)
    job.refresh_from_db()
    assert job.status == "ERROR" and "preserved" in job.error
    assert client.get(endpoint(analysis)).json()["body"] == "Keep my manual edits"


def test_generation_rejects_foreign_topic_and_unknown_sources(client, analysis, drafting_runtime, environment):
    from uuid import uuid4

    from core.discussion import run_job

    other = Request.objects.create(environment=environment, need="Unrelated")
    foreign = RequestMessage.objects.create(request=other, role="user", kind="need", content="Foreign question")
    assert client.get(endpoint(analysis), {"topic_message_id": foreign.pk}).status_code == 404
    assert enqueue_draft(client, analysis).status_code == 200
    job = Job.objects.get()
    job.status = "RUNNING"
    job.save()
    with pytest.raises(ValueError, match="unknown conversation source"):
        run_job(job, lambda *args, **kwargs: {"session_id":str(uuid4()), "output":{"title":"False source", "body":"Claim", "sources":["message:9999999"]}})
    assert "ticket_preparation" not in Request.objects.get(pk=analysis.pk).discussion_state


def test_cancelled_drafting_does_not_become_an_ordinary_discussion_retry(client, analysis):
    assert enqueue_draft(client, analysis).status_code == 200
    assert client.post(f"/api/analyses/{analysis.pk}/discussion/cancel").status_code == 200
    analysis.refresh_from_db()
    response = client.post(f"/api/analyses/{analysis.pk}/discussion", {
        "message":"", "expected_revision":analysis.discussion_state["revision"], "restart_session":True,
    }, content_type="application/json")
    assert response.status_code == 409 and "ticket preparation" in response.json()["detail"]


def test_selected_answer_uses_its_own_clarifications_in_a_long_conversation(client,analysis,monkeypatch):
    for index in range(45):
        RequestMessage.objects.create(request=analysis,role="user",kind="discussion",content=f"UNRELATED_TOPIC_{index}")
        RequestMessage.objects.create(request=analysis,role="assistant",kind="discussion_reply",content=f"UNRELATED_FINDING_{index}")
    question=RequestMessage.objects.create(request=analysis,role="user",kind="discussion",content="Prevent invalid periods.")
    clarification=RequestMessage.objects.create(request=analysis,role="assistant",kind="clarification",content="Include archived records?")
    answer=RequestMessage.objects.create(request=analysis,role="user",kind="answer",content="Yes, archived records too.")
    anchor=RequestMessage.objects.create(request=analysis,role="assistant",kind="discussion_reply",content="Period validation is missing in the import.")
    RequestMessage.objects.create(request=analysis,role="user",kind="discussion",content="UNRELATED_NEW_QUESTION")
    RequestMessage.objects.create(request=analysis,role="assistant",kind="discussion_reply",content="UNRELATED_NEW_ANSWER")
    row=client.get(endpoint(analysis),{"new_ticket":True,"anchor_message_id":anchor.pk}).json()
    assert row["anchor_message_id"]==anchor.pk and row["topic_message_id"]==question.pk
    assert row["context_message_ids"]==[question.pk,clarification.pk,answer.pk,anchor.pk]
    assert row["topics"]==[] and row["source_version"] is None
    saved=save(client,analysis,row,topic_message_id=question.pk,anchor_message_id=anchor.pk).json()
    response=client.post(endpoint(analysis)+"/generate",{"ticket_id":saved["id"],"expected_revision":saved["revision"],
      "expected_discussion_revision":saved["discussion_revision"],"topic_message_id":question.pk,"anchor_message_id":anchor.pk},content_type="application/json")
    assert response.status_code==200,response.content
    job=Job.objects.get(kind="discussion")
    inputs=job.payload["ticket_preparation"]["inputs"]
    assert "Yes, archived records too." in str(inputs)
    assert "Period validation is missing" in str(inputs)
    assert "UNRELATED_" not in str(inputs)
    assert not AnalysisRun.objects.exists() and not analysis.business_decisions.exists()
