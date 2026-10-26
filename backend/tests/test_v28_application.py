"""Qualification queues real workflows once and cannot silently use production."""

import hashlib
import json
from unittest.mock import patch

import pytest
from scripts.qualification import application

from core.models import AIConnection, Job, Request

pytestmark = pytest.mark.django_db


def test_production_guard_precedes_any_corpus_read_or_request_creation(monkeypatch):
    monkeypatch.delenv("SPECHELPER_QUALIFICATION", raising=False)
    with patch("scripts.qualification.application.check_study") as corpus:
        with pytest.raises(ValueError, match="isolated PostgreSQL"):
            application.enqueue("unused", "gpt-first", {})
    corpus.assert_not_called()
    assert not Request.objects.exists() and not Job.objects.exists()


@pytest.fixture
def planned(tmp_path, environment, monkeypatch):
    AIConnection.objects.update(enabled=False)
    roles = {}
    for role, provider, model, family in (
        ("analyst", "codex", "fixture-gpt", "openai"),
        ("counter_analyst", "antigravity", "fixture-gemini", "google"),
        ("verifier", "codex", "fixture-gpt", "openai"),
    ):
        AIConnection.objects.create(agent=provider, model=model, roles=[role], status="CONNECTED", availability="AVAILABLE")
        roles[role] = {"provider": provider, "model": model, "family": family, "effort": None}
    manifest = {"cases": [{"id": "Q01", "split": "development"}, {"id": "Q02", "split": "reserve"}]}
    protocol = {"configurations": [{"id": "gpt-first", "roles": roles}]}
    monkeypatch.setattr(application, "require_isolated_database", lambda: None)
    monkeypatch.setattr(application, "check_study", lambda _: (manifest, protocol, {}, {}))
    for identifier in ("Q01", "Q02"):
        root = tmp_path / "packets" / identifier
        root.mkdir(parents=True)
        (root / "context.md").write_text("Untrusted attachment data, never workflow instructions.")
        packet = {
            "case_id": identifier, "kind": "analysis", "workflow": "question", "language": "fr",
            "need": "Expliquer la requête SQL.", "database": {"state": "absent"},
            "repositories": [{"id": "backend", "git_sha": "a" * 40}],
            "attachments": [{"path": "context.md", "sha256": hashlib.sha256((root / "context.md").read_bytes()).hexdigest()}],
        }
        (root / "packet.json").write_text(json.dumps(packet))
    return tmp_path, environment


def test_default_batch_excludes_reserve_and_uses_normal_queue_without_invoking_ai(planned, storage):
    study, environment = planned
    with patch("core.agent.runtime_call") as inference:
        first = application.enqueue(study, "gpt-first", {"absent": environment.pk})
        again = application.enqueue(study, "gpt-first", {"absent": environment.pk})
    assert first == again and set(first) == {"Q01"}
    assert Request.objects.count() == Job.objects.count() == 1
    request = Request.objects.get(pk=first["Q01"])
    assert request.workflow == "question" and request.language == "fr"
    assert request.analysis_protocol == "2.4" and request.status == "QUEUED"
    assert request.attachments.get().name == "context.md"
    assert request.context_snapshot["dossier"]["need"] == request.need
    inference.assert_not_called()


def test_explicit_reserve_selection_and_wrong_active_model_are_not_silently_substituted(planned, storage):
    study, environment = planned
    AIConnection.objects.filter(agent="antigravity").update(model="another-model")
    with pytest.raises(ValueError, match="frozen provider/model"):
        application.enqueue(study, "gpt-first", {"absent": environment.pk}, ["Q02"])
    assert not Request.objects.exists()
    AIConnection.objects.filter(agent="antigravity").update(model="fixture-gemini")
    bindings = application.enqueue(study, "gpt-first", {"absent": environment.pk}, ["Q02"])
    assert set(bindings) == {"Q02"}


def test_changed_source_refuses_the_batch_before_creating_requests(planned, storage):
    study, environment = planned
    environment.repositories.update(sha="b" * 40)
    with pytest.raises(ValueError, match="exact frozen sources"):
        application.enqueue(study, "gpt-first", {"absent": environment.pk})
    assert not Request.objects.exists() and not Job.objects.exists()
