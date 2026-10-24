"""Human-only business decisions, explicit conflicts and frozen queued revisions."""

import copy
import json

import pytest
from pydantic import ValidationError

from core.business_decisions import prepare_questions, snapshot_for_request
from core.clarification_schema import ClarificationQuestion
from core.models import BusinessDecision, BusinessValidation, Job, Request, ResultVersion

pytestmark = pytest.mark.django_db


def option(key, behavior):
    return {
        "id": key,
        "label": behavior,
        "behavior": behavior,
        "relevance": "Applies when benefits are still open.",
        "benefits": "Keeps the closing rule explicit.",
        "limitations": "Requires an operational check.",
        "consequences": "The closing action follows this business rule.",
    }


def question(**changes):
    return {
        "id": "termination",
        "question": "What happens when benefits remain open?",
        "kind": "choice",
        "decision_key": "open-benefits",
        "reason": "This changes when the contract can be closed.",
        "options": [
            option("a", "Block termination."),
            option("b", "Allow termination with a warning."),
        ],
        **changes,
    }


def waiting(environment, workflow="request", questions=None):
    """Seed a historical clarification, including older records with an empty context."""
    return Request.objects.create(
        environment=environment,
        environment_name_snapshot=environment.name,
        need="Clarify contract termination behavior.",
        workflow=workflow,
        status="NEEDS_CLARIFICATION",
        questions=questions or [question()],
    )


def send(client, path, value, method="post"):
    return getattr(client, method)(path, data=json.dumps(value), content_type="application/json")


def answer(client, request, **changes):
    prefix = "questions" if request.workflow == "question" else "requests"
    return send(
        client,
        f"/api/{prefix}/{request.pk}/answers",
        {
            "answers": {},
            "choices": {"termination": {"option_id": "b"}},
            "expected_decision_revision": request.decision_revision,
            **changes,
        },
    )


def settle(request, number=1):
    """Seed a completed-result fixture for decision API tests, without invoking publication.

    Current publication fencing and mandatory review are exercised by the v2.4
    workflow suite, not by these business validation/optimistic revision units.
    """
    request.refresh_from_db()
    request.status = "READY"
    request.save(update_fields=["status"])
    Job.objects.filter(target=str(request.pk)).update(status="DONE")
    run = request.analysis_runs.order_by("-number").first()
    if run:
        run.status = "READY"
        run.save(update_fields=["status"])
    return ResultVersion.objects.create(
        request=request,
        run=run,
        number=number,
        status="READY",
        environment_name=request.environment_name_snapshot,
        decisions_snapshot=snapshot_for_request(request)["decisions"],
        context_snapshot=copy.deepcopy(request.context_snapshot),
    )


@pytest.mark.parametrize("workflow", ["request", "question"])
def test_guided_choice_is_recorded_in_order_and_resumes_shared_queue(client, environment, workflow):
    request = waiting(environment, workflow)
    result = answer(client, request)
    assert result.status_code == 200, result.content
    data = result.json()
    assert data["status"] == "QUEUED" and data["decision_revision"] == 1
    assert data["analysis_protocol"] == "2.4"
    assert data["decisions"][0]["option_id"] == "b"
    assert data["decisions"][0]["value"] == "Allow termination with a warning."
    assert data["decisions"][0]["sequence"] == 1
    assert data["decision_history"] == data["decisions"]
    request.refresh_from_db()
    run = request.analysis_runs.get()
    assert run.job.kind == "analysis" and run.job.status == "QUEUED"
    assert run.job.payload["analysis_protocol"] == "2.4"
    assert run.orchestration["version"] == "2.4"
    assert run.orchestration["outputs"] == {}
    assert run.context_snapshot["business_decisions"]["decisions"][0]["option_id"] == "b"
    assert run.job.payload["changed_decision_keys"] == ["open-benefits"]
    assert request.conversation[-1]["answers"]["termination"] == "Allow termination with a warning."


def test_empty_historical_context_can_upgrade_to_current_public_protocol(client, environment):
    request = waiting(environment)
    assert request.context_snapshot == {} and request.analysis_protocol == "legacy"
    response = answer(client, request)
    assert response.status_code == 200, response.content
    request.refresh_from_db()
    assert request.analysis_protocol == "2.4"
    assert request.context_snapshot["instructions"]["mode"] == "factual"
    assert request.context_snapshot["business_decisions"]["decisions"][0]["option_id"] == "b"


@pytest.mark.parametrize(
    "choice",
    [{"option_id": "other"}, {"option_id": "other", "text": " "}, {"option_id": "unknown"}],
)
def test_other_requires_a_real_answer_and_unknown_options_are_rejected(client, environment, choice):
    request = waiting(environment)
    result = answer(client, request, choices={"termination": choice})
    assert result.status_code == 422, result.content
    assert not BusinessDecision.objects.exists() and not Job.objects.exists()
    request.refresh_from_db()
    assert request.status == "NEEDS_CLARIFICATION" and request.decision_revision == 0


def test_other_text_is_preserved_as_user_business_rule(client, environment):
    request = waiting(environment)
    result = answer(
        client,
        request,
        choices={
            "termination": {
                "option_id": "other",
                "text": "Suspend closing until a supervisor approves.",
            }
        },
    )
    assert result.status_code == 200, result.content
    assert result.json()["decisions"][0]["value"] == "Suspend closing until a supervisor approves."
    assert result.json()["decisions"][0]["option"] is None


def test_open_question_keeps_legacy_free_answer_without_fake_choices(client, environment):
    request = waiting(
        environment, questions=[{"id": "scope", "question": "Which contracts are in scope?"}]
    )
    result = send(
        client,
        f"/api/requests/{request.pk}/answers",
        {"answers": {"scope": "Active contracts only."}},
    )
    assert result.status_code == 200, result.content
    row = result.json()["decisions"][0]
    assert row["option_id"] is None and row["option"] is None
    assert row["question"] == {"id": "scope", "question": "Which contracts are in scope?"}
    assert row["value"] == "Active contracts only."


def test_choice_cannot_be_submitted_as_a_display_label_or_without_revision(client, environment):
    request = waiting(environment)
    result = send(
        client,
        f"/api/requests/{request.pk}/answers",
        {"answers": {"termination": "Allow termination with a warning."}},
    )
    assert result.status_code == 422
    result = send(
        client,
        f"/api/requests/{request.pk}/answers",
        {"choices": {"termination": {"option_id": "b"}}},
    )
    assert result.status_code == 409
    assert not BusinessDecision.objects.exists()


def test_conflicting_answer_does_not_modify_rule_until_explicit_confirmation(client, environment):
    request = waiting(environment)
    assert answer(client, request).status_code == 200
    first = BusinessDecision.objects.get()
    request.refresh_from_db()
    request.status = "NEEDS_CLARIFICATION"
    request.questions = [
        question(
            conflicts_with=first.pk,
            reason="Your new answer differs from the confirmed warning rule.",
        )
    ]
    request.save()
    # Seed the later user-waiting checkpoint consistently on both persisted states.
    # Merely changing Request.status would describe a still-queued, non-paused job.
    run = request.analysis_runs.get()
    run.status = "NEEDS_CLARIFICATION"
    run.orchestration.update(checkpoint="requirement", current_role="analyst")
    run.save(update_fields=["status", "orchestration"])
    Job.objects.filter(pk=run.job_id).update(status="DONE")
    changed = answer(client, request, choices={"termination": {"option_id": "a"}})
    assert changed.status_code == 409, changed.content
    assert changed.json()["code"] == "DECISION_CONFLICT"
    assert changed.json()["conflicts"][0]["previous"]["option_id"] == "b"
    assert changed.json()["conflicts"][0]["proposed"]["option_id"] == "a"
    assert BusinessDecision.objects.count() == 1
    confirmed = answer(
        client, request, choices={"termination": {"option_id": "a"}}, confirm_changes=True
    )
    assert confirmed.status_code == 200, confirmed.content
    rows = confirmed.json()["decision_history"]
    assert [row["option_id"] for row in rows] == ["b", "a"]
    assert rows[-1]["previous_id"] == first.pk
    assert [row["sequence"] for row in rows] == [1, 2]
    assert confirmed.json()["decisions"] == [rows[-1]]
    first.refresh_from_db()
    assert first.option_id == "b"
    with pytest.raises(ValueError, match="immutable"):
        first.save()


def test_stale_and_duplicate_browser_answers_cannot_append_decisions(client, environment):
    request = waiting(environment)
    stale = answer(client, request, expected_decision_revision=99)
    assert stale.status_code == 409
    assert answer(client, request).status_code == 200
    assert answer(client, request).status_code == 409
    assert BusinessDecision.objects.count() == 1


def test_decision_revision_queues_focused_reanalysis_and_preserves_old_result(client, environment):
    request = waiting(environment)
    assert answer(client, request).status_code == 200
    previous = settle(request)
    original = copy.deepcopy(previous.decisions_snapshot)
    row = BusinessDecision.objects.get()
    path = f"/api/requests/{request.pk}/decisions/{row.pk}/revise"
    payload = {"option_id": "a", "expected_decision_revision": 1, "expected_version": 1}
    preview = send(client, path, payload)
    assert preview.status_code == 409 and preview.json()["code"] == "DECISION_CONFLICT"
    assert request.analysis_runs.count() == 1
    revised = send(client, path, {**payload, "confirm_change": True})
    assert revised.status_code == 200, revised.content
    request.refresh_from_db()
    run = request.analysis_runs.order_by("-number").first()
    assert request.analysis_protocol == "2.4"
    assert run.job.payload["analysis_protocol"] == "2.4"
    assert run.orchestration["version"] == "2.4"
    assert run.job.payload["changed_decision_keys"] == ["open-benefits"]
    assert run.context_snapshot["changed_decision_keys"] == ["open-benefits"]
    assert run.context_snapshot["business_decisions"]["decisions"][0]["option_id"] == "a"
    assert revised.json()["decisions"][0]["source_version"] == 1
    previous.refresh_from_db()
    assert previous.decisions_snapshot == original
    assert previous.decisions_snapshot[0]["option_id"] == "b"
    replaced = send(
        client, path, {**payload, "expected_decision_revision": 2, "confirm_change": True}
    )
    assert replaced.status_code == 409


@pytest.mark.parametrize("workflow", ["request", "question"])
def test_business_validation_locks_changes_until_explicit_reopening(client, environment, workflow):
    request = waiting(environment, workflow)
    assert answer(client, request).status_code == 200
    settle(request)
    prefix = "questions" if workflow == "question" else "requests"
    payload = {"expected_version": 1, "expected_decision_revision": 1}
    path = f"/api/{prefix}/{request.pk}/validation"
    approved = send(client, path, payload)
    assert approved.status_code == 200, approved.content
    assert approved.json()["validated_version"] == 1
    row = BusinessDecision.objects.get()
    revision = send(
        client,
        f"/api/{prefix}/{request.pk}/decisions/{row.pk}/revise",
        {"expected_decision_revision": 1, "option_id": "a", "confirm_change": True},
    )
    assert revision.status_code == 409
    continuation = send(
        client,
        f"/api/{prefix}/{request.pk}/continue",
        {"message": "Change the closing rule.", "expected_version": 1},
    )
    assert continuation.status_code == 409
    reopened = send(client, path, payload, "delete")
    assert reopened.status_code == 200, reopened.content
    assert reopened.json()["validated_version"] is None
    assert list(BusinessValidation.objects.values_list("action", flat=True)) == [
        "validated",
        "reopened",
    ]
    with pytest.raises(ValueError, match="immutable"):
        BusinessValidation.objects.first().save()


def test_validation_rejects_partial_stale_and_busy_results(client, environment):
    request = waiting(environment)
    assert answer(client, request).status_code == 200
    version = settle(request)
    payload = {"expected_version": 1, "expected_decision_revision": 1}
    path = f"/api/requests/{request.pk}/validation"
    assert send(client, path, {**payload, "expected_version": 99}).status_code == 409
    assert send(client, path, {**payload, "expected_decision_revision": 0}).status_code == 409
    ResultVersion.objects.filter(pk=version.pk).update(status="PARTIAL")
    assert send(client, path, payload).status_code == 409
    Request.objects.filter(pk=request.pk).update(status="ANALYZING")
    assert send(client, path, payload).status_code == 409
    assert not BusinessValidation.objects.exists()


def test_conflict_references_cannot_cross_requests_or_restore_old_decision(client, environment):
    first = waiting(environment)
    assert answer(client, first).status_code == 200
    row = BusinessDecision.objects.get()
    other = waiting(environment)
    with pytest.raises(ValueError, match="unavailable business decision"):
        prepare_questions(other, [question(conflicts_with=row.pk)])
    prepared = prepare_questions(
        first, [question(decision_key="injected-key", conflicts_with=row.pk)]
    )
    assert prepared[0]["decision_key"] == "open-benefits"


@pytest.mark.parametrize(
    "changes",
    [
        {"options": [option("a", "A")]},
        {"options": [option("a", "A"), option("a", "B")]},
        {"options": [option("a", "A"), option("b", "B"), option("c", "C"), option("d", "D")]},
        {"options": [option("other", "Other"), option("b", "B")]},
        {"options": [{**option("a", "A"), "limitations": ""}, option("b", "B")]},
        {"options": [{**option("a", "A"), "recommended": True}, option("b", "B")]},
        {"kind": "free"},
        {"conflicts_with": 1, "reason": ""},
    ],
)
def test_question_schema_limits_options_and_requires_business_explanations(changes):
    with pytest.raises(ValidationError):
        ClarificationQuestion.model_validate(question(**changes))


def test_known_and_recognizable_credentials_are_never_stored_as_business_rules(
    client, environment, monkeypatch
):
    request = waiting(environment)
    secret = "synthetic-private-business-answer-secret"
    monkeypatch.setattr("core.sensitive_data.configured_secrets", lambda: [secret])
    result = answer(
        client, request, choices={"termination": {"option_id": "other", "text": secret}}
    )
    assert result.status_code == 422
    assert secret.encode() not in result.content
    result = answer(
        client,
        request,
        choices={"termination": {"option_id": "other", "text": "github_pat_" + "a" * 30}},
    )
    assert result.status_code == 422
    assert not BusinessDecision.objects.exists()


def test_all_new_mutations_require_remote_authentication(client, settings, environment):
    settings.ACCESS_LOCAL_ONLY = False
    settings.ACCESS_PASSWORD_HASH = "pbkdf2_sha256$600000$salt$hash"
    request = waiting(environment)
    for path, payload in [
        (
            f"/api/requests/{request.pk}/decisions/1/revise",
            {"expected_decision_revision": 0, "text": "A rule"},
        ),
        (
            f"/api/requests/{request.pk}/validation",
            {"expected_version": 1, "expected_decision_revision": 0},
        ),
    ]:
        assert send(client, path, payload).status_code == 401


def test_revision_requires_latest_result_number_even_when_decision_revision_is_current(
    client, environment
):
    request = waiting(environment)
    assert answer(client, request).status_code == 200
    settle(request)
    row = BusinessDecision.objects.get()
    path = f"/api/requests/{request.pk}/decisions/{row.pk}/revise"
    missing_version = send(
        client, path, {"option_id": "a", "expected_decision_revision": 1, "confirm_change": True}
    )
    assert missing_version.status_code == 409
    assert BusinessDecision.objects.count() == 1


def test_validation_refuses_a_result_that_does_not_contain_current_confirmed_rules(
    client, environment
):
    request = waiting(environment)
    assert answer(client, request).status_code == 200
    version = settle(request)
    ResultVersion.objects.filter(pk=version.pk).update(decisions_snapshot=[])
    result = send(
        client,
        f"/api/requests/{request.pk}/validation",
        {"expected_version": 1, "expected_decision_revision": 1},
    )
    assert result.status_code == 409
    assert not BusinessValidation.objects.exists()
