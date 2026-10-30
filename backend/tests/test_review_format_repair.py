"""Contradictory review statuses get one schema-specific correction, never coercion."""

import pytest
from pydantic import ValidationError
from test_v15_flow import assessment
from test_v17_flow import execute, report

from core.analysis_flow import Review
from core.models import Request
from core.services import enqueue_analysis

pytestmark = pytest.mark.django_db


def inconsistent_review():
    return {"status":"APPROVED", "summary":"A source check is still needed.", "issues":[],
            "verification":{"target":"code", "questions":["Does selection check the active flag?"]}, "questions":[]}


@pytest.mark.parametrize("repaired", [True, False])
def test_question_comparison_preserves_focused_check_and_bounded_repair(environment, storage, repaired):
    value = Request.objects.create(environment=environment, workflow="question", need="How are active records selected?", confrontation=True)
    enqueue_analysis(value.pk)
    invalid = inconsistent_review()
    corrected = {**invalid, "status":"NEEDS_VERIFICATION"}
    responses = [assessment(), report(), report(), invalid, corrected if repaired else invalid]
    if repaired:
        responses += [
            {"answers":[{"question":"Does selection check the active flag?", "answer":"Yes", "evidence":["contracts/export.py: export_active"]}], "remaining_uncertainties":[]},
            {"agreements":[], "divergences":[], "result":{"status":"PARTIAL", "answer":{"title":"Active selection", "summary":"Active rows are selected; the full caller scope was not verified."}}},
        ]
    calls = execute(value, storage, responses)
    repairs = [call for call in calls if "FORMAT CORRECTION" in call["prompt"]]
    assert len(repairs) == 1, (value.status, value.error, [(call["profile"],call["schema"]["title"]) for call in calls])
    assert repairs[0]["schema"]["title"] == "Review"
    assert "APPROVED requires verification=null" in repairs[0]["prompt"]
    assert "preserve it and use NEEDS_VERIFICATION" in repairs[0]["prompt"]
    assert "The answer field must be a JSON object" not in repairs[0]["prompt"]
    run = value.analysis_runs.get()
    assert {"requirement", "analyst", "counter_independent"} <= run.orchestration["outputs"].keys()
    if repaired:
        assert value.status == "PARTIAL", value.error
        assert run.orchestration["outputs"]["comparison"]["verification"] == invalid["verification"]
        assert "focused_verification" in run.orchestration["outputs"]
        assert len(calls) == 7
        assert value.versions.count() == 1
    else:
        assert value.status == "ERROR"
        assert len(calls) == 5
        assert "comparison" not in run.orchestration["outputs"]
        assert not value.versions.exists()


def test_contradiction_is_not_silently_normalized():
    with pytest.raises(ValidationError, match="Missing or unexpected focused verification"):
        Review.model_validate(inconsistent_review())
