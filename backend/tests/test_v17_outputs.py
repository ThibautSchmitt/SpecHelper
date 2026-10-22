"""Question exports preserve selected evidence and exclude uncurated runtime data."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.question_outputs import (
    QuestionAnswer,
    QuestionOutput,
    QuestionReference,
    QuestionReport,
    render_answer,
    render_document,
    render_transfer,
)


@pytest.fixture
def explanation():
    return {
        "title": "Contract renewal",
        "summary": "Active contracts renew after an eligibility check.",
        "business_explanation": "An eligible customer keeps their current benefits.",
        "technical_explanation": "RenewalService checks eligibility before persisting renewal.",
        "verified_facts": ["Inactive contracts are excluded by the active predicate."],
        "rules": ["The contract must be active."],
        "steps": ["Check eligibility, then renew."],
        "examples": ["An inactive contract is rejected."],
        "dependencies": ["RenewalService calls EligibilityPolicy."],
        "flows": ["Contract API → RenewalService → repository."],
        "inferences": ["The policy may also support batch renewals; the caller was not inspected."],
        "uncertainties": ["The nightly scheduler has not been verified."],
        "references": [
            {
                "repository": "team/contracts",
                "path": "contracts/renewal.py",
                "symbol": "RenewalService.renew",
            }
        ],
    }


@pytest.fixture
def baseline():
    return [{"repository": "team/contracts", "branch": "release/2", "sha": "b" * 40}]


def test_consolidated_answer_preserves_evidence_limits_and_frozen_references(explanation, baseline):
    value = render_answer(explanation, baseline)
    assert "Inactive contracts are excluded" in value
    assert "## Inferences" in value
    assert "## Uncertainties and verification limits" in value
    assert "contracts/renewal.py" in value
    assert "RenewalService.renew" in value
    assert "release/2" in value
    assert "b" * 40 in value
    assert value == render_document(explanation, baseline, "mixed")


def test_document_formats_prioritize_distinct_useful_content(explanation, baseline):
    business = render_document(explanation, baseline, "business")
    technical = render_document(explanation, baseline, "technical")
    mixed = render_document(explanation, baseline, "mixed")
    assert "## Business rules" in business
    assert "An inactive contract is rejected." in business
    assert "## Technical explanation" not in business
    assert "## Modules and dependencies" in technical
    assert "## Processing and data flows" in technical
    assert "## Business explanation" not in technical
    assert "## Business explanation" in mixed and "## Technical explanation" in mixed
    for result in (business, technical, mixed):
        assert "nightly scheduler" in result and "b" * 40 in result


def test_transfer_contains_only_selected_conclusions_and_explicit_provenance(explanation, baseline):
    original = deepcopy(explanation)
    output = render_transfer(
        "How does renewal work?",
        explanation,
        baseline,
        version=3,
        request_id="93206b30-4473-49a6-9952-69058a02b785",
        created_at=datetime(2026, 10, 22, tzinfo=UTC),
    )
    assert "How does renewal work?" in output
    assert "Answer version: 3" in output
    assert "93206b30-4473-49a6-9952-69058a02b785" in output
    assert "2026-10-22T00:00:00+00:00" in output
    assert "Recheck its conclusions" in output
    assert "explicitly describe the desired change" in output
    assert "## Inferences" in output and "nightly scheduler" in output
    assert explanation == original


def test_unknown_raw_dialogue_and_internal_notes_are_rejected(explanation, baseline):
    for field in ("conversation", "messages", "internal_notes", "raw_documents", "password"):
        enriched = {**explanation, field: "confidential content"}
        with pytest.raises(ValidationError):
            render_transfer("What happens?", enriched, baseline, version=1)


@pytest.mark.parametrize(
    "path",
    [
        "../private.py",
        "contracts/../private.py",
        "/session/notes.md",
        "/tmp/output.md",
        "/data/context.md",
        "C:\\Users\\secret.txt",
        "src\\contracts.py",
        "src//contracts.py",
        "src/./contracts.py",
        "src/%2e%2e/secrets.py",
        "src/%252e%252e/secrets.py",
        "src/a\nsecret.py",
    ],
)
def test_reference_paths_cannot_escape_repository_or_inject_markdown(path):
    with pytest.raises(ValidationError):
        QuestionReference(repository="team/contracts", path=path)


@pytest.mark.parametrize("path", ["src/tmp/cache.py", "data/schema.sql", "module/file name.py"])
def test_legitimate_relative_paths_are_preserved(path):
    assert QuestionReference(repository="team/contracts", path=path).path == path


@pytest.mark.parametrize(
    "path", ["/session/notes", "/tmp/trace", "/Users/person/token", "C:\\tmp\\x"]
)
def test_private_runtime_paths_are_rejected_from_prose(explanation, baseline, path):
    explanation["uncertainties"] = ["See " + path]
    with pytest.raises(ValidationError):
        render_answer(explanation, baseline)
    with pytest.raises(ValueError):
        render_transfer("Check " + path, {"title": "Answer", "summary": "Bounded"}, [], version=1)


def test_unknown_baseline_and_agent_supplied_shas_are_rejected(explanation):
    with pytest.raises(ValueError, match="frozen Git baseline"):
        render_answer(explanation, [])
    reference = explanation["references"][0]
    with pytest.raises(ValidationError):
        QuestionReference.model_validate({**reference, "sha": "a" * 40})


def test_no_references_explicitly_reports_missing_verification():
    value = render_answer(
        {"title": "Limited answer", "summary": "No sources could be checked."}, []
    )
    assert "No source references were verified" in value


def test_schema_bounds_and_duplicate_clarification_ids(explanation):
    with pytest.raises(ValidationError):
        QuestionAnswer.model_validate({**explanation, "verified_facts": ["x"] * 31})
    with pytest.raises(ValidationError):
        QuestionAnswer.model_validate({**explanation, "rules": ["x" * 4001]})
    with pytest.raises(ValidationError):
        QuestionReport.model_validate(
            {
                "observed_behavior": "Needs a use-case clarification.",
                "questions": [
                    {"id": "case", "question": "Which use case?"},
                    {"id": "case", "question": "Which customer?"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        QuestionOutput.model_validate({"status": "READY", "answer": explanation, "ticket": {}})


def test_aggregate_narrative_budgets_prevent_unbounded_handoffs(explanation):
    with pytest.raises(ValidationError, match="narrative budget"):
        QuestionAnswer.model_validate({**explanation, "verified_facts": ["x" * 4000] * 16})
    with pytest.raises(ValidationError, match="narrative budget"):
        QuestionReport.model_validate(
            {"observed_behavior": "Observed", "evidence": ["x" * 4000] * 8}
        )


def test_unsupported_format_and_invalid_provenance_are_rejected(explanation, baseline):
    with pytest.raises(ValueError, match="Unsupported"):
        render_document(explanation, baseline, "pdf")
    for version in (0, -1, True, "1"):
        with pytest.raises(ValueError, match="positive integer"):
            render_transfer("Question?", explanation, baseline, version=version)
    with pytest.raises(ValueError):
        render_transfer(
            "Question?", explanation, baseline, version=1, request_id="/session/private"
        )


def test_french_exports_translate_headings_and_transfer_instructions(explanation, baseline):
    # Narrative text is supplied in the chosen language by the analysis; headings are application text.
    output = render_transfer(
        "Comment fonctionne le renouvellement ?", explanation, baseline, version=2, language="fr"
    )
    assert "## Faits vérifiés" in output
    assert "## Références des sources" in output
    assert "Version de réponse : 2" in output
    assert "Revérifiez" in output
    assert "contracts/renewal.py" in output and "b" * 40 in output
