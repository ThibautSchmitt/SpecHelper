"""Private qualification inputs retain provenance, real commits and blind packets."""
import json
import shutil

import pytest
from scripts.qualification import harness

from tests.test_v28_qualification import protocol


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / "private-inputs"
    root.mkdir()
    shutil.copytree(harness.HERE / "fixtures", root / "fixtures")
    corpus, expected = harness.load_corpus()
    corpus["origin"] = "anonymized_project_cases"
    corpus["repository_directories"] = ["contracts", "billing", "portal", "reporting"]
    corpus["database_observation_period"] = "2024-01-01/2025-12-31"
    for case in corpus["cases"]:
        case["provenance"] = {
            "origin": "anonymized_request", "source_request_id": "PRIVATE_ORIGIN_"+case["id"],
            "privacy_review": {"status": "REVIEWED", "reviewer": "Fixture privacy reviewer",
                               "method": "manual_anonymization", "notes": "Authored test record; no customer data."},
        }
    expected["cases"]["Q01"]["required_facts"][0]["statement"] += " PRIVATE_EXPECTATION_MARKER"
    harness.write_json(root / "corpus.json", corpus)
    harness.write_json(root / "expectations.json", expected)
    return root


def test_private_provenance_requires_an_explicit_privacy_record_without_inventing_human_approval(inputs):
    corpus, _ = harness.load_corpus(inputs)
    assert corpus["human_validation"] == "PENDING"
    corpus["cases"][0]["provenance"].pop("privacy_review")
    harness.write_json(inputs / "corpus.json", corpus)
    with pytest.raises(ValueError, match="privacy review"):
        harness.load_corpus(inputs)


def test_private_git_sources_keep_original_commits_and_answers_stay_outside_packets(inputs, tmp_path):
    repository = inputs / "fixtures/contracts"
    harness.git(repository, "init", "-q", "--initial-branch=main")
    harness.git(repository, "config", "user.name", "Private fixture author")
    harness.git(repository, "config", "user.email", "fixture@example.invalid")
    harness.git(repository, "add", "--all")
    harness.git(repository, "commit", "-qm", "test: original private source")
    original = harness.git(repository, "rev-parse", "HEAD")
    public_hash = harness.digest(harness.read_json(harness.HERE / "corpus.json"))
    study = tmp_path / "study"
    harness.prepare(study, protocol(), inputs=inputs)
    harness.check_study(study)
    packet = harness.read_json(study / "packets/Q01/packet.json")
    assert next(row for row in packet["repositories"] if row["id"] == "contracts")["git_sha"] == original
    assert "PRIVATE_ORIGIN" not in json.dumps(packet)
    assert "PRIVATE_EXPECTATION" not in json.dumps(packet)
    assert "PRIVATE_EXPECTATION" not in "\n".join(path.read_text() for path in (study / "packets").rglob("*.json") if ".git" not in path.parts)
    assert harness.read_json(study / "evaluator/corpus.json")["origin"] == "anonymized_project_cases"
    assert public_hash == harness.digest(harness.read_json(harness.HERE / "corpus.json"))
    review = tmp_path / "review.md"
    harness.export_review(study, review)
    assert "private corpus" in review.read_text()
    assert "authored synthetic business rules" not in review.read_text()
    assert not harness.human_reviewed(study, harness.read_json(study / "manifest.json"), "Q01")


def test_dirty_private_git_source_is_rejected_before_creating_a_study(inputs, tmp_path):
    repository = inputs / "fixtures/contracts"
    harness.git(repository, "init", "-q")
    harness.git(repository, "config", "user.name", "Private fixture author")
    harness.git(repository, "config", "user.email", "fixture@example.invalid")
    harness.git(repository, "add", "--all")
    harness.git(repository, "commit", "-qm", "test: original private source")
    (repository / "untracked-private-note").write_text("This must not enter an analysis packet.")
    with pytest.raises(ValueError, match="clean repository roots"):
        harness.prepare(tmp_path / "study", protocol(), inputs=inputs)
    assert not (tmp_path / "study").exists()


@pytest.mark.parametrize("invalid", ["case_path", "repository_path", "link", "missing_period"])
def test_private_import_rejects_paths_links_and_unknown_database_period(inputs, tmp_path, invalid):
    corpus = harness.read_json(inputs / "corpus.json")
    if invalid == "case_path":
        old = corpus["cases"][0]["id"]
        corpus["cases"][0]["id"] = "../escape"
        expected = harness.read_json(inputs / "expectations.json")
        expected["cases"]["../escape"] = expected["cases"].pop(old)
        harness.write_json(inputs / "expectations.json", expected)
    elif invalid == "repository_path":
        corpus["repository_directories"] = ["../private"]
    elif invalid == "link":
        (inputs / "fixtures/contracts/secret-link").symlink_to(inputs / "expectations.json")
    else:
        corpus.pop("database_observation_period")
    harness.write_json(inputs / "corpus.json", corpus)
    with pytest.raises(ValueError):
        harness.prepare(tmp_path / "study", protocol(), inputs=inputs)
    assert not (tmp_path / "escape").exists()
