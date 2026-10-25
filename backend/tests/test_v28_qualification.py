"""Qualification evidence stays frozen, blind, independently reviewed and honest."""

import json
import shutil

import pytest
from scripts.qualification import harness


def protocol():
    codex = {"provider": "codex", "model": "fixture-gpt", "family": "openai", "effort": None, "cli_version": "fixture-1"}
    gemini = {"provider": "antigravity", "model": "fixture-gemini", "family": "google", "effort": None, "cli_version": "fixture-2"}
    return {"instructions": "Independent source reading and mandatory counter-analysis.", "skills": [],
            "tool_policy": {"sources": "read_only", "database": "read_only", "web": False},
            "configurations": [
                {"id": "gpt-first", "roles": {"analyst": codex, "counter_analyst": gemini, "verifier": codex}},
                {"id": "gemini-first", "roles": {"analyst": gemini, "counter_analyst": codex, "verifier": gemini}},
            ]}


@pytest.fixture(scope="module")
def frozen(tmp_path_factory):
    path = tmp_path_factory.mktemp("qualification")
    harness.prepare(path, protocol())
    return path


@pytest.fixture
def study(tmp_path, frozen):
    path = tmp_path / "study"
    shutil.copytree(frozen, path)
    return path


def run_records(study):
    manifest, configuration, corpus, _ = harness.check_study(study)
    cases = {case["id"]: case for case in corpus["cases"]}
    runs = []
    for config in configuration["configurations"]:
        rows = []
        for row in manifest["cases"]:
            definition = cases[row["id"]]
            attempts = [] if definition["kind"] == "scope" else [
                {"role": role, "context_id": config["id"] + ":" + row["id"] + ":" + role,
                 "status": "SUCCESS", "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
                for role in sorted(harness.ROLES)
            ]
            rows.append({"case_id": row["id"], "packet_sha256": row["packet_sha256"],
                         "status": "COMPLETE", "attempts": attempts, "elapsed_seconds": 1.0,
                         "scope_status": "IN_SCOPE", "output": {"claims": []}})
        runs.append({"configuration_id": config["id"], "manifest_sha256": harness.digest(manifest), "cases": rows})
    return runs


def test_corpus_is_varied_and_explicitly_unreviewed_not_relabelled_customer_data():
    corpus, expected = harness.load_corpus()
    assert len(corpus["cases"]) == 24
    assert sum(case["split"] == "reserve" for case in corpus["cases"]) == 6
    assert corpus["human_validation"] == "PENDING"
    assert {case["workflow"] for case in corpus["cases"]} == {"question", "request"}
    assert all(case["provenance"]["origin"] == "authored_synthetic" for case in corpus["cases"])
    assert all(value["human_review"]["status"] == "PENDING" for value in expected["cases"].values())


def test_agent_packets_never_contain_answers_tags_reviews_or_database_rows(study):
    manifest, _, _, _ = harness.check_study(study)
    for row in manifest["cases"]:
        packet = harness.read_json(study / "packets" / row["id"] / "packet.json")
        assert not set(packet) & {"expected", "required_facts", "dangerous_omissions", "title", "tags", "split", "review"}
        assert not (study / "packets" / row["id"] / "expectations.json").exists()
        assert not (study / "packets" / row["id"] / "database/data.json").exists()
    assert (study / "evaluator/database/data.json").is_file()


@pytest.mark.parametrize("alter", ["source", "extra", "database", "expected", "protocol"])
def test_modified_sha_answer_data_and_unexpected_files_invalidate_the_study(study, alter):
    paths = {
        "source": "packets/Q01/repositories/contracts/policy.py", "extra": "packets/Q01/answers.txt",
        "database": "evaluator/database/data.json", "expected": "evaluator/expectations.json",
        "protocol": "protocol.json",
    }
    path = study / paths[alter]
    if path.exists():
        path.write_text(path.read_text() + "\n")
    else:
        path.write_text("Evaluator answers must never be here.")
    if alter in {"expected", "protocol"}:
        value = json.loads(path.read_text())
        value["altered"] = True
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        harness.check_study(study)


def test_no_semantic_review_means_unknown_errors_not_zero_or_a_quality_score(study):
    result = harness.compare(study, run_records(study), [])
    assert result["qualification_status"] == "NOT_QUALIFIED"
    for config in result["configurations"]:
        assert config["material_errors"] is None and config["decisive_omissions"] is None
        assert config["monetary_cost"] is None
        assert config["reviewed_cases"] == 0 and config["human_approved_cases"] == 0
        assert "confidence" not in config and "score" not in config


def test_missing_independent_role_or_reused_context_cannot_count_as_complete(study):
    runs = run_records(study)
    runs[0]["cases"][0]["attempts"].pop()
    with pytest.raises(ValueError, match="three"):
        harness.compare(study, runs, [])
    runs = run_records(study)
    runs[0]["cases"][0]["attempts"][1]["context_id"] = runs[0]["cases"][0]["attempts"][0]["context_id"]
    with pytest.raises(ValueError, match="independent"):
        harness.compare(study, runs, [])


def test_unknown_usage_is_not_filled_with_zero_and_scope_cases_have_no_model_attempts(study):
    runs = run_records(study)
    runs[0]["cases"][0]["attempts"][0]["usage"] = {}
    result = harness.compare(study, runs, [])
    assert result["configurations"][0]["usage"]["input_tokens"] is None
    runs[0]["cases"][16]["attempts"] = [{"role": "analyst", "context_id": "extra", "status": "SUCCESS"}]
    with pytest.raises(ValueError, match="scope cases"):
        harness.compare(study, runs, [])


def test_review_must_bind_exact_output_and_account_for_all_material_facts(study):
    runs = run_records(study)
    review = {"configuration_id": "gpt-first", "case_id": "Q01", "packet_sha256": runs[0]["cases"][0]["packet_sha256"],
              "output_sha256": "wrong", "reviewer": "Independent fixture reviewer", "method": "independent_source_audit",
              "facts": [], "all_material_claims_reviewed": True}
    with pytest.raises(ValueError, match="Independent review"):
        harness.compare(study, runs, [review])


def test_recording_review_requires_explicit_human_attestation_and_does_not_change_packets(study):
    manifest = harness.check_study(study)[0]
    with pytest.raises(ValueError, match="human reviewer"):
        harness.approve(study, reviewer="", business_familiarity="", attestation="", case_ids=["Q01"])
    # This is a test-only receipt, not a claim that the delivery corpus was approved.
    harness.approve(study, reviewer="Fixture human", business_familiarity="Fixture domain", attestation="Test-only approval", case_ids=["Q01"])
    assert harness.human_reviewed(study, manifest, "Q01") is True
    assert harness.human_reviewed(study, manifest, "Q02") is False
    assert harness.check_study(study)[0] == manifest


def test_human_review_document_contains_expected_rules_and_explicit_limits(study, tmp_path):
    path = tmp_path / "review.md"
    harness.export_review(study, path)
    text = path.read_text()
    assert "Q24" in text and "Q01-F1" in text
    assert "PENDING" in text and "authored synthetic" in text
    assert "every future answer" in text


def test_identical_family_effort_distributions_are_not_two_comparison_configurations():
    value = protocol()
    value["configurations"][1]["roles"] = value["configurations"][0]["roles"]
    with pytest.raises(ValueError, match="family distribution"):
        harness.validate_protocol(value)
