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
    assert not draft["publication_available"]
    response = save(client, analysis, draft, title="Prevent invalid periods", body="Show an error.")
    assert response.status_code == 200, response.content
    assert response.json()["revision"] == 1
    reopened = client.get(endpoint(analysis)).json()
    assert reopened["body"] == "Show an error."
    assert "Unverified draft" in reopened["markdown"]
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
    assert "unverified" in draft["body"] and "UNVERIFIED_ASSISTANT_HYPOTHESIS" not in draft["body"]
    response = save(client, analysis, draft, scope_choice="clarified")
    assert response.status_code == 200
    assert "have not been independently verified" in response.json()["markdown"]
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
    assert not draft["source_verified"] and not draft["publication_allowed"]
    response = save(client, analysis, draft)
    assert response.status_code == 200
    assert "Unverified draft" in response.json()["markdown"]
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
