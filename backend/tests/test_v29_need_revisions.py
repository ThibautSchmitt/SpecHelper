"""Late business edits preserve history and invalidate publication until reassessed."""

from uuid import uuid4

import pytest
from django.utils import timezone

from core.business_decisions import snapshot_for_request
from core.models import AnalysisRun, BusinessDecision, Job, Request, RequestMessage, ResultVersion
from core.ticket_presentation import publication_blockers

pytestmark = pytest.mark.django_db


def prepared(environment):
    value = Request.objects.create(environment=environment, need="Explain the SQL export.",
                                   workflow="question", status="READY", analysis_protocol="2.4")
    BusinessDecision.objects.create(request=value, sequence=1, revision=0, key="scope", question={}, value="Active contracts only")
    version = ResultVersion.objects.create(request=value, number=1, status="READY", explanation={"title": "Original explanation"},
                                           decisions_snapshot=snapshot_for_request(value)["decisions"])
    return value, version


def payload(**changes):
    return {"need": "Explain the SQL export and its archived contract exception.",
            "expected_revision": 0, "expected_version": 1, "expected_decision_revision": 0,
            "operation_id": str(uuid4()), **changes}


def edit(client, value, data):
    return client.post(f"/api/analyses/{value.pk}/need", data, content_type="application/json")


def test_late_edit_preserves_results_decisions_and_starts_fresh_three_role_cycle(client, environment):
    value, version = prepared(environment)
    response = edit(client, value, payload())
    assert response.status_code == 200, response.content
    result = response.json()
    assert result["original_need"] == "Explain the SQL export."
    assert result["need_revision"] == 1 and result["conclusions_stale"]
    assert result["latest_version"]["number"] == 1
    assert result["decisions"][0]["value"] == "Active contracts only"
    value.refresh_from_db()
    version.refresh_from_db()
    assert version.explanation == {"title": "Original explanation"}
    assert value.workflow == "question" and value.status == "QUEUED"
    run = value.analysis_runs.get()
    assert run.orchestration["outputs"] == {} and run.orchestration["version"] == "2.4"
    assert run.context_snapshot["dossier"]["need"] == value.need
    assert run.context_snapshot["dossier"]["need_revision"] == 1
    assert run.context_snapshot["business_decisions"]["decisions"][0]["value"] == "Active contracts only"
    assert "The need changed after this result. Reanalyze before publication." in publication_blockers(version)
    ResultVersion.objects.create(request=value, number=2, status="READY")
    assert not client.get(f"/api/analyses/{value.pk}").json()["conclusions_stale"]


def test_retry_is_idempotent_even_after_the_reanalysis_started(client, environment):
    value, _ = prepared(environment)
    data = payload()
    assert edit(client, value, data).status_code == 200
    assert edit(client, value, data).status_code == 200
    assert value.messages.filter(kind="need_revision").count() == 1
    assert Job.objects.filter(target=str(value.pk)).count() == 1
    assert edit(client, value, {**data, "need": "Explain a different export."}).status_code == 409


@pytest.mark.parametrize("changes", [{"expected_revision": 1}, {"expected_version": 2}, {"expected_decision_revision": 1}])
def test_concurrent_changes_cannot_overwrite_a_newer_dossier(client, environment, changes):
    value, _ = prepared(environment)
    assert edit(client, value, payload(**changes)).status_code == 409
    value.refresh_from_db()
    assert value.need == "Explain the SQL export."
    assert not Job.objects.exists() and not value.messages.filter(kind="need_revision").exists()


def test_pending_clarification_is_retained_in_revision_and_never_resumed(client, environment):
    value, _ = prepared(environment)
    value.status, value.questions = "NEEDS_CLARIFICATION", [{"id": "old", "question": "Old question?"}]
    value.save()
    prior = AnalysisRun.objects.create(request=value, number=1, status="NEEDS_CLARIFICATION", orchestration={"outputs": {"requirement": {"old": True}}})
    assert edit(client, value, payload()).status_code == 200
    prior.refresh_from_db()
    assert prior.orchestration["outputs"] == {"requirement": {"old": True}}
    assert value.messages.get(kind="need_revision").data["previous_questions"][0]["id"] == "old"
    value.refresh_from_db()
    assert value.questions == [] and value.analysis_runs.count() == 2


def test_out_of_scope_revision_is_saved_without_ai_but_keeps_prior_result_stale(client, environment):
    value, _ = prepared(environment)
    response = edit(client, value, payload(need="Give me an apple pie recipe."))
    assert response.status_code == 200
    assert response.json()["scope_assessment"]["status"] == "OUT_OF_SCOPE"
    assert response.json()["conclusions_stale"] and response.json()["status"] == "DRAFT"
    assert not Job.objects.exists()


@pytest.mark.parametrize("status,validated", [("ANALYZING", None), ("READY", 1)])
def test_busy_and_validated_requests_require_explicit_safe_transition(client, environment, status, validated):
    value, _ = prepared(environment)
    Request.objects.filter(pk=value.pk).update(status=status, validated_version=validated)
    assert edit(client, value, payload()).status_code == 409
    assert not value.messages.filter(kind="need_revision").exists()


def test_stale_result_cannot_be_validated_even_when_state_is_ready(client, environment):
    value, _ = prepared(environment)
    RequestMessage.objects.create(request=value, role="user", kind="need_revision", content="Changed export.")
    # Legacy READY state or a delayed client cannot approve the previous answer.
    response = client.post(f"/api/questions/{value.pk}/validation", {
        "expected_version": 1, "expected_decision_revision": 0,
    }, content_type="application/json")
    assert response.status_code == 409
    assert response.json()["detail"] == "The need changed after this result. Reanalyze before validation."
    assert value.messages.filter(created_at__lte=timezone.now()).exists()
