"""Guided business choices survive real queue resumes, roles and artifact publication."""

import copy
import uuid
from unittest.mock import patch

import pytest
from ninja.errors import HttpError

from core.business_decisions import DecisionConflict
from core.models import Request
from core.services import continue_conversation, enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


def choice(**updates):
    return {
        "id": "ongoing-benefits",
        "decision_key": "termination-benefits",
        "kind": "choice",
        "question": "What should happen when benefits are still ongoing?",
        "reason": "The selected rule changes whether the user can complete termination.",
        "unknowns": ["The intended termination rule has not been confirmed."],
        "options": [
            {
                "id": "a",
                "label": "Block termination",
                "behavior": "Block termination while benefits are ongoing.",
                "relevance": "Use when closure must remain consistent.",
                "benefits": "Prevents premature closure.",
                "limitations": "Can delay termination indefinitely.",
                "consequences": "The case owner must close ongoing benefits first.",
            },
            {
                "id": "b",
                "label": "Allow with a warning",
                "behavior": "Allow termination with a warning about ongoing benefits.",
                "relevance": "Use when case owners need flexibility.",
                "benefits": "Keeps termination available.",
                "limitations": "Requires users to acknowledge the warning.",
                "consequences": "Case owners remain responsible for ongoing benefits.",
            },
        ],
        **updates,
    }


def assessment(questions=None, complexity="simple", **extra):
    return {
        "status": "NEEDS_CLARIFICATION" if questions else "READY_TO_ANALYZE",
        "understanding": "Clarify termination with ongoing benefits.",
        "questions": questions or [],
        "ticket": None,
        "complexity": complexity,
        **extra,
    }


def execute(request, storage, outputs):
    calls = []

    def caller(path, payload, **kwargs):
        calls.append(payload)
        assert outputs, "The orchestrator made an unexpected provider call"
        return {"session_id": payload["session_id"] or str(uuid.uuid4()), "output": outputs.pop(0)}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=caller),
    ):
        job = claim_job()
        assert job is not None
        perform_job(job)
        job.refresh_from_db()
    request.refresh_from_db()
    return calls, job


def resume_legacy(request, **payload):
    """Resume historical engine fixtures through the service, preserving legacy protocol.

    Public answer endpoints deliberately adopt v2.3 and are covered by v2.3 tests.
    These controlled provider outputs exercise persisted legacy orchestration only.
    """
    request.refresh_from_db()
    assert request.analysis_protocol == "legacy"
    value = enqueue_analysis(request.pk, **payload)
    assert value.analysis_protocol == "legacy"
    return value


def started(environment, **values):
    request = Request.objects.create(
        environment=environment,
        need="Clarify termination with ongoing benefits.",
        language="en",
        **values,
    )
    enqueue_analysis(request.pk)
    return request


@pytest.mark.parametrize("workflow", ["request", "question"])
def test_choice_b_other_and_dependent_question_resume_without_ai_business_approval(
    environment, storage, bundle, code_report, workflow
):
    request = started(environment, workflow=workflow)
    _, job = execute(request, storage, [assessment([choice()])])
    assert request.status == "NEEDS_CLARIFICATION" and job.status == "DONE"
    assert not request.versions.exists() and claim_job() is None
    first_snapshot = copy.deepcopy(request.context_snapshot)
    with pytest.raises(HttpError) as invalid:
        resume_legacy(
            request,
            choices={"ongoing-benefits": {"option_id": "other"}},
            expected_decision_revision=0,
        )
    assert invalid.value.status_code == 422
    assert request.business_decisions.count() == 0
    resume_legacy(
        request,
        choices={"ongoing-benefits": {"option_id": "b"}},
        expected_decision_revision=0,
    )
    request.refresh_from_db()
    assert request.decision_revision == 1
    selected = choice()["options"][1]["behavior"]
    dependent = {
        "id": "warning",
        "decision_key": "warning-text",
        "question": "What warning should the case owner see?",
    }
    calls, job = execute(request, storage, [assessment([dependent])])
    assert selected in calls[0]["prompt"]
    assert "Do not repeat a question already answered" in calls[0]["prompt"]
    assert request.status == "NEEDS_CLARIFICATION" and request.questions == [dependent]
    assert request.context_snapshot["library"] == first_snapshot["library"]
    resume_legacy(
        request,
        answers={"warning": "The case owner must review all ongoing benefits."},
        expected_decision_revision=1,
    )
    if workflow == "request":
        result = bundle.model_dump()
        # An unchosen alternative in model prose cannot become a confirmed rule.
        result["ticket"]["expected_behavior"] = [choice()["options"][0]["behavior"]]
        result["ticket"]["acceptance_criteria"] = [choice()["options"][0]["behavior"]]
        report = code_report
    else:
        result = {
            "status": "READY",
            "answer": {
                "title": "Termination rules",
                "summary": "The case owner receives the confirmed warning.",
            },
        }
        report = {"observed_behavior": "The current process blocks termination.", "questions": []}
    calls, job = execute(request, storage, [assessment(), {"analysis": report, "result": result}])
    assert request.status == "READY", request.error
    assert job.status == "DONE" and len(calls) == 2
    version = request.versions.get()
    assert len(version.decisions_snapshot) == 2
    for artifact in version.artifacts.all():
        assert selected in artifact.content
        assert "The case owner must review all ongoing benefits." in artifact.content
        assert choice()["options"][0]["behavior"] not in artifact.content


@pytest.mark.parametrize("path", ["simple", "standard", "analyst", "counter"])
def test_source_discovery_can_pause_every_analysis_path_before_writing(
    environment, storage, code_report, path
):
    request = started(environment, confrontation=path in {"analyst", "counter"})
    report = {**code_report, "questions": [choice()]}
    values = [assessment(complexity="simple" if path == "simple" else "standard")]
    if path == "simple":
        values.append({"analysis": report, "result": None})
    else:
        if path == "counter":
            values.append(code_report)
        values.append(report)
    calls, job = execute(request, storage, values)
    assert request.status == "NEEDS_CLARIFICATION", request.error
    assert job.status == "DONE" and not request.versions.exists()
    assert request.questions[0]["kind"] == "choice"
    assert calls[-1]["phase"] == "analysis"
    assert claim_job() is None


def test_reviewer_can_raise_a_business_conflict_instead_of_approving_it(
    environment, storage, code_report
):
    request = started(environment)
    _, job = execute(
        request,
        storage,
        [
            assessment(complexity="standard"),
            code_report,
            {
                "review": {
                    "status": "NEEDS_CLARIFICATION",
                    "summary": "The business rule needs a human choice.",
                    "issues": [],
                    "verification": None,
                    "questions": [choice()],
                },
                "result": None,
            },
        ],
    )
    assert request.status == "NEEDS_CLARIFICATION", request.error
    assert job.status == "DONE" and not request.versions.exists()


def test_a_late_writer_question_cannot_publish_an_unapproved_result(
    environment, storage, code_report, bundle
):
    request = started(environment)
    output = bundle.model_dump()
    output["questions"] = [choice()]
    execute(request, storage, [assessment(), {"analysis": code_report, "result": output}])
    assert request.status == "NEEDS_CLARIFICATION", request.error
    assert not request.versions.exists()


def test_a_changed_rule_requires_confirmation_and_reanalysis_keeps_old_artifacts(
    environment, storage, code_report, bundle
):
    request = started(environment)
    execute(request, storage, [assessment([choice()])])
    resume_legacy(
        request,
        choices={"ongoing-benefits": {"option_id": "b"}},
        expected_decision_revision=0,
    )
    execute(
        request, storage, [assessment(), {"analysis": code_report, "result": bundle.model_dump()}]
    )
    previous = request.versions.get()
    old_goal = previous.artifacts.get(name="goal.md").content
    decision = request.business_decisions.get()
    continue_conversation(request.pk, "Instead block termination until benefits end.", 1)
    conflict = choice(
        conflicts_with=decision.pk,
        reason="The new request conflicts with allowing termination with a warning.",
    )
    execute(request, storage, [assessment([conflict])])
    changed = {"choices": {"ongoing-benefits": {"option_id": "a"}}, "expected_decision_revision": 1}
    with pytest.raises(DecisionConflict) as conflict_error:
        resume_legacy(request, **changed)
    assert conflict_error.value.status_code == 409
    assert request.business_decisions.count() == 1
    resume_legacy(request, **changed, confirm_changes=True)
    calls, _ = execute(
        request, storage, [assessment(), {"analysis": code_report, "result": bundle.model_dump()}]
    )
    assert request.status == "READY", request.error
    assert all('"targeted_reanalysis": true' in call["prompt"] for call in calls)
    assert all(
        '"changed_decision_keys": ["termination-benefits"]' in call["prompt"] for call in calls
    )
    assert (
        request.versions.get(number=2).decisions_snapshot[0]["value"]
        == choice()["options"][0]["behavior"]
    )
    assert previous.artifacts.get(name="goal.md").content == old_goal
    assert len(request.versions.get(number=1).decisions_snapshot) == 1


def test_assumptions_remain_qualified_and_unknown_summary_fields_stay_empty(
    environment, storage, code_report, bundle
):
    request = started(environment)
    unknown = "The source does not establish whether a warning needs a justification."
    preliminary = assessment(
        findings=[
            {
                "kind": "assumption",
                "description": unknown,
                "business_impact": "The expected warning behavior may differ.",
                "evidence": [],
            }
        ],
        business_summary={"desired": "Allow termination with a warning."},
    )
    later_unknown = "Historical exceptions were not verified."
    reported = {**code_report, "business_summary": {"uncertainties": [later_unknown]}}
    calls, _ = execute(
        request, storage, [preliminary, {"analysis": reported, "result": bundle.model_dump()}]
    )
    assert request.status == "READY", request.error
    summary = request.versions.get().business_summary
    assert summary["current"] == ""
    assert summary["uncertainties"] == ["Assumption: " + unknown, later_unknown]
    assert unknown in request.versions.get().artifacts.get(name="ticket.md").content
    assert "confirmed_decisions" in calls[-1]["prompt"]


def test_a_clear_request_uses_no_artificial_multiple_choice_card(
    environment, storage, code_report, bundle
):
    request = started(environment)
    calls, _ = execute(
        request, storage, [assessment(), {"analysis": code_report, "result": bundle.model_dump()}]
    )
    assert request.status == "READY" and request.questions == []
    assert len(calls) == 2 and not request.business_decisions.exists()


def test_repeated_answered_question_is_repaired_once_without_asking_the_user_again(
    environment, storage, bundle, code_report
):
    request = started(environment)
    execute(request, storage, [assessment([choice()])])
    resume_legacy(
        request,
        choices={"ongoing-benefits": {"option_id": "b"}},
        expected_decision_revision=0,
    )
    calls, _ = execute(
        request,
        storage,
        [
            assessment([choice()]),
            assessment(),
            {"analysis": code_report, "result": bundle.model_dump()},
        ],
    )
    assert request.status == "READY", request.error
    assert len(calls) == 3
    assert "BUSINESS QUESTION CORRECTION" in calls[1]["prompt"]
    assert request.business_decisions.count() == 1


def test_reused_verified_facts_keep_their_unresolved_business_limits(
    environment, storage, bundle, code_report
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.services import add_attachment

    request = Request.objects.create(
        environment=environment, need="Clarify the export scope.", confrontation=True, language="en"
    )
    add_attachment(request.pk, SimpleUploadedFile("rules.txt", b"Synthetic export rules."))
    enqueue_analysis(request.pk)
    unknown = "Historical exception handling remains unverified."
    question = {"id": "scope", "question": "Which contract scope is needed?"}
    execute(
        request,
        storage,
        [
            assessment(complexity="standard", business_summary={"uncertainties": [unknown]}),
            {"observations": [], "questions": [question]},
        ],
    )
    resume_legacy(
        request,
        answers={"scope": "Include active contracts only."},
        expected_decision_revision=0,
    )
    calls, _ = execute(
        request,
        storage,
        [
            code_report,
            code_report,
            {
                "status": "APPROVED",
                "summary": "Evidence reviewed.",
                "issues": [],
                "verification": None,
            },
            {"agreements": [], "divergences": [], "result": bundle.model_dump()},
        ],
    )
    assert request.status == "READY", request.error
    assert calls[0]["profile"] == "code"
    assert unknown in request.versions.get().business_summary["uncertainties"]
