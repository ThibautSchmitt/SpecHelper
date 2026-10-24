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
