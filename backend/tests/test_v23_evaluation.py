"""Optional indexes cannot replace fixed sources or manufacture quality/usage evidence."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reliability_benchmark", ROOT / "scripts/evaluation/reliability_benchmark.py"
)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_fixed_fixture_snapshots_are_reproducible_and_unmodified(tmp_path):
    first = benchmark.prepare(tmp_path / "first")
    second = benchmark.prepare(tmp_path / "second")
    assert first == second
    for expected in first["cases"]:
        benchmark.check_snapshot(tmp_path / "first/repos" / expected["id"], expected)


def test_reusing_nonempty_destination_cannot_overwrite_data(tmp_path):
    destination = tmp_path / "study"
    destination.mkdir()
    (destination / "keep.txt").write_text("preserved")
    with pytest.raises(ValueError, match="empty"):
        benchmark.prepare(destination)
    assert (destination / "keep.txt").read_text() == "preserved"


@pytest.mark.parametrize("change", ["commit", "content", "repository"])
def test_wrong_index_snapshot_or_repository_is_rejected(tmp_path, change):
    manifest = benchmark.prepare(tmp_path / "study")
    expected = manifest["cases"][0]
    repository = tmp_path / "study/repos" / expected["id"]
    index = {"case_id": expected["id"], "git_sha": expected["git_sha"], "files": expected["files"]}
    if change == "commit":
        index["git_sha"] = "0" * 40
    elif change == "content":
        (repository / "policy.py").write_text("unreviewed replacement")
    else:
        index["case_id"] = "another-environment"
    with pytest.raises(ValueError, match="snapshot|changed"):
        benchmark.check_snapshot(repository, expected, index)


def test_missing_inference_usage_is_not_estimated_from_source_bytes(tmp_path):
    benchmark.prepare(tmp_path / "study")
    for case in benchmark.cases():
        result = benchmark.source_navigation(tmp_path / "study", case["id"])
        assert result["source_recall"] == 1
        assert result["input_tokens"] is None and result["cost"] is None
        assert not result["inference_performed"]
    report = benchmark.compare(tmp_path / "study")
    assert not report["complete_analysis_comparison"]
    assert report["index_enabled_for_production"] is False
    assert all(row["quality"] is None for row in report["measurements"])


def test_an_index_result_cannot_read_another_repository(tmp_path):
    manifest = benchmark.prepare(tmp_path / "study")
    expected = manifest["cases"][0]
    case = benchmark.cases()[0]
    with pytest.raises(ValueError, match="another repository"):
        benchmark.navigation_result(
            tmp_path / "study/repos" / expected["id"],
            case,
            expected,
            "source",
            ["../another-environment/private.py"],
            0.1,
        )


def test_literal_screening_does_not_claim_human_semantic_precision():
    case = benchmark.cases()[0]
    response = {
        "conclusions": [
            {
                "statement": "Cancellation is always blocked",
                "status": "supported",
                "sources": ["policy.py"],
            }
        ]
    }
    result = benchmark.score_response(case, response)
    assert result["literal_screen_precision"] == 0
    assert result["precision"] is None and result["material_error_rate"] is None
    assert result["critical_omissions"]


def test_semantic_review_must_cover_every_material_conclusion():
    case = benchmark.cases()[0]
    response = {
        "conclusions": [
            {
                "statement": "The rule is conditional.",
                "status": "supported",
                "sources": ["policy.py"],
            }
        ]
    }
    review = {
        "reviewer": "synthetic-reviewer",
        "method": "Inspected frozen source and fixture truth",
        "material_conclusions": 1,
        "material_errors": 0,
    }
    result = benchmark.score_response(case, response, review)
    assert result["precision"] == 1
    invalid = copy.deepcopy(review)
    invalid["material_conclusions"] = 0
    with pytest.raises(ValueError, match="every returned"):
        benchmark.score_response(case, response, invalid)


def test_semantic_fact_review_can_recognize_paraphrases_without_relabeling_literal_checks():
    case = benchmark.cases()[0]
    output = {
        "conclusions": [
            {
                "id": "C1",
                "statement": "An ordinary purchase may be cancelled with a running service; imports have a separate path.",
                "status": "supported",
                "sources": ["policy.py", "history.py", "records.json", "settings.py"],
            }
        ]
    }
    review = {
        "reviewer": "accountable-source-reviewer",
        "method": "Reopened frozen source and checked every claim and corpus fact.",
        "material_conclusions": 1,
        "material_errors": 0,
        "conclusion_reviews": [
            {
                "claim_id": "C1",
                "material_error": False,
                "reason": "The source predicate and separate importer support the qualified statement.",
            }
        ],
        "critical_fact_reviews": [
            {
                "id": fact["id"],
                "covered": True,
                "claim_ids": ["C1"],
                "reason": "Coverage audited from the complete claim and its cited frozen sources.",
            }
            for fact in case["critical_facts"]
        ],
        "counterexample_reviews": [
            {
                "id": value,
                "covered": True,
                "claim_ids": ["C1"],
                "reason": "The qualified ordinary-purchase/import paths are explicit.",
            }
            for value in case["expected_counterexamples"]
        ],
        "unresolved_business_decisions": 0,
        "business_decision_reason": "This fixture asks for observed behavior, not a policy choice.",
    }
    quality = benchmark.score_response(case, output, review)
    assert quality["critical_omissions"]  # Literal words are absent; the distinction is preserved.
    assert quality["semantic_critical_omissions"] == []
    assert quality["semantic_unresolved_business_decisions"] == 0
    invalid = copy.deepcopy(review)
    invalid["critical_fact_reviews"][0]["claim_ids"] = ["invented"]
    with pytest.raises(ValueError, match="frozen corpus"):
        benchmark.score_response(case, output, invalid)


def test_semantic_coverage_remains_unknown_without_explicit_review():
    quality = benchmark.score_response(
        benchmark.cases()[0],
        {
            "conclusions": [
                {"statement": "A qualified rule.", "status": "partial", "sources": ["policy.py"]}
            ]
        },
    )
    assert quality["semantic_critical_omissions"] is None
    assert quality["semantic_counterexamples_detected"] is None
    assert quality["semantic_unresolved_business_decisions"] is None


def test_native_role_citation_audit_checks_actual_excerpt_and_commit(tmp_path):
    study = tmp_path / "study"
    manifest = benchmark.prepare(study)
    case = manifest["cases"][0]
    path = "policy.py"
    excerpt = (study / "repos" / case["id"] / path).read_text().splitlines()[0]
    source = {
        "kind": "git",
        "repository": case["id"],
        "commit": case["git_sha"],
        "path": path,
        "line_start": 1,
        "line_end": 1,
        "excerpt": excerpt,
    }
    output = {
        "claims": [
            {
                "id": "C1",
                "statement": "A bounded source observation.",
                "status": "supported",
                "sources": [source],
            }
        ]
    }
    response = {
        "case_id": case["id"],
        "mode": "source",
        "git_sha": case["git_sha"],
        "output": output,
        "role_outputs": [output],
    }
    assert benchmark.audit_native_sources(study, [response])["invalid_sources"] == 0
    source["excerpt"] = "invented excerpt"
    assert benchmark.audit_native_sources(study, [response])["invalid_sources"] == 1
    source["excerpt"] = excerpt
    source["commit"] = "0" * 40
    assert benchmark.audit_native_sources(study, [response])["invalid_sources"] == 1


def test_complete_measurements_cannot_pass_quality_gate_with_invalid_native_citation(tmp_path):
    study = tmp_path / "study"
    manifest = benchmark.prepare(study)
    responses = []
    for case in benchmark.cases():
        navigation = benchmark.source_navigation(study, case["id"])
        expected = next(item for item in manifest["cases"] if item["id"] == case["id"])
        path = case["expected_files"][0]
        excerpt = (study / "repos" / case["id"] / path).read_text().splitlines()[0]
        for mode in ("source", "codebase-memory-mcp"):
            # Controlled records test the report gate, not actual MCP/provider performance.
            benchmark.write_json(
                study / "navigation" / f"{case['id']}-{mode}.json", {**navigation, "mode": mode}
            )
            output = {
                "claims": [
                    {
                        "id": "C1",
                        "statement": "Controlled test claim.",
                        "status": "supported",
                        "sources": [
                            {
                                "kind": "git",
                                "repository": case["id"],
                                "commit": expected["git_sha"],
                                "path": path,
                                "line_start": 1,
                                "line_end": 1,
                                "excerpt": excerpt,
                            }
                        ],
                    }
                ]
            }
            review = {
                "reviewer": "controlled-test-fixture",
                "method": "Tests gate separation only, not native quality.",
                "material_conclusions": 1,
                "material_errors": 0,
                "critical_fact_reviews": [
                    {
                        "id": fact["id"],
                        "covered": True,
                        "claim_ids": ["C1"],
                        "reason": "Controlled coverage fixture.",
                    }
                    for fact in case["critical_facts"]
                ],
                "counterexample_reviews": [
                    {
                        "id": value,
                        "covered": True,
                        "claim_ids": ["C1"],
                        "reason": "Controlled coverage fixture.",
                    }
                    for value in case["expected_counterexamples"]
                ],
                "unresolved_business_decisions": 0,
                "business_decision_reason": "Controlled fixture.",
            }
            responses.append(
                {
                    "case_id": case["id"],
                    "mode": mode,
                    "git_sha": expected["git_sha"],
                    "output": output,
                    "review": review,
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost": None,
                }
            )
    benchmark.write_json(study / "responses.json", responses)
    passing = benchmark.compare(study, study / "responses.json")
    assert passing["complete_analysis_comparison"] and passing["native_quality_gate_passed"]
    responses[0]["output"]["claims"][0]["sources"][0]["excerpt"] = "incorrect native excerpt"
    benchmark.write_json(study / "responses.json", responses)
    failing = benchmark.compare(study, study / "responses.json")
    assert failing["complete_analysis_comparison"]
    assert not failing["native_quality_gate_passed"]
    assert failing["source_provenance"]["invalid_sources"] == 1
