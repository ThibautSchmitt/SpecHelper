"""Mandatory independent roles, provenance, counterexamples and bounded context."""

import json
import subprocess
import uuid
from unittest.mock import patch

import pytest

from core.models import AIConnection, InstanceSettings, Request
from core.orchestration_settings import get_config
from core.providers import identity_for
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def repository(environment, storage):
    path = storage / "company/backend"
    path.mkdir(parents=True)
    (path / "export.py").write_text(
        "def selected(rows):\n    return [row for row in rows if row.active]\n"
    )
    for args in (
        ["init", "-q"],
        ["add", "export.py"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    sha = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    environment.repositories.update(sha=sha)
    return {
        "kind": "git",
        "repository": "company/backend",
        "commit": sha,
        "path": "export.py",
        "symbol": "selected",
        "line_start": 1,
        "line_end": 2,
        "excerpt": (path / "export.py").read_text().strip(),
    }


def claim(source, **changes):
    return {
        "id": "active",
        "statement": "The configured export selects active rows.",
        "kind": "observed",
        "status": "supported",
        "scope": {
            "environment": "Staging",
            "conditions": ["The inspected selected function is used."],
            "period": "Current frozen code",
            "population": "Rows passed to selected",
            "sample_limits": "Only the inspected function was verified.",
        },
        "sources": [source],
        "counterexamples": [],
        "verification_notes": "The filter is visible in the exact source excerpt.",
        "universal": False,
        "material": True,
        **changes,
    }


def requirement():
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Explain active exports.",
        "questions": [],
        "ticket": None,
        "complexity": "simple",
    }


def source_report(source, workflow="request", **changes):
    common = {"claims": [claim(source)], "questions": []}
    if workflow == "question":
        return {
            **common,
            "observed_behavior": "Active rows are selected.",
            "evidence": ["export.py:selected"],
            **changes,
        }
    return {
        **common,
        "current_behavior": "Active rows are selected.",
        "proposed_solution": "Keep the confirmed filter.",
        "evidence": ["export.py:selected"],
        "impacts": ["Export scope"],
        "database_impact": "No database changes",
        "risks": [],
        "tests_expected": ["Check active filtering."],
        "uncertainties": [],
        **changes,
    }


def verification(source, **changes):
    return {
        "report": {
            "claims": [claim(source, id="analyst:active"), claim(source, id="counter:active")],
            "database": {"status": "checked", "scope": "Untrusted claimed scope"},
            "limitations": [],
            "blocking": False,
            **changes,
        },
        "questions": [],
    }


def outputs(source, bundle, workflow="request", verified=None):
    final = (
        bundle.model_dump()
        if workflow == "request"
        else {
            "status": "READY",
            "answer": {
                "title": "Active export",
                "summary": "The configured export selects active rows.",
                "verified_facts": ["The filter checks active status."],
            },
        }
    )
    return [
        requirement(),
        source_report(source, workflow, uncertainties=["PRIVATE_ANALYST_NOTE"]),
        source_report(source, workflow),
        {
            "status": "APPROVED",
            "summary": "Ready for independent verification.",
            "issues": [],
            "verification": None,
        },
        verified or verification(source),
        final,
    ]


def execute(request, storage, values):
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(payload)
        assert values, "Unexpected provider call"
        value = values.pop(0)
        return {"output": value, "session_id": payload["session_id"] or str(uuid.uuid4())}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        job = claim_job()
        assert job
        perform_job(job)
        job.refresh_from_db()
    request.refresh_from_db()
    return calls, job


def start(environment, workflow="request"):
    """Exercise persisted v2.3 work; public creation now deliberately selects v2.4."""
    from core.services import enqueue_analysis

    InstanceSettings.objects.update_or_create(pk=1, defaults={"language": "en"})
    value = Request.objects.create(
        environment=environment,
        workflow=workflow,
        analysis_protocol="2.3",
        need="Explain the configured export scope.",
        language="en",
    )
    enqueue_analysis(value.pk)
    return value


@pytest.mark.parametrize("workflow", ["request", "question"])
@pytest.mark.parametrize("two_families", [False, True])
def test_three_roles_remain_mandatory_for_simple_and_self_approved_analyses(
    environment, storage, repository, bundle, workflow, two_families
):
    InstanceSettings.objects.update_or_create(
        pk=1, defaults={"allow_confrontation": False, "orchestration": {"verifier_enabled": False}}
    )
    if two_families:
        other = AIConnection.objects.create(
            agent="claude", status="CONNECTED", availability="AVAILABLE"
        )
        identity_for(other)
    request = start(environment, workflow)
    calls, job = execute(request, storage, outputs(repository, bundle, workflow))
    assert request.status == "READY", request.error
    assert job.status == "DONE" and len(calls) == 6
    assert [call["public_role"] for call in calls] == [
        "analyst",
        "analyst",
        "counter_analyst",
        "counter_analyst",
        "verifier",
        "verifier",
    ]
    assert len({call["context_id"] for call in calls}) == 3
    assert calls[0]["context_id"] == calls[1]["context_id"]
    assert calls[2]["context_id"] == calls[3]["context_id"]
    assert calls[4]["context_id"] == calls[5]["context_id"]
    assert "PRIVATE_ANALYST_NOTE" not in calls[2]["prompt"]
    assert "PRIVATE_ANALYST_NOTE" in calls[3]["prompt"]
    assert "counterexamples" in calls[4]["prompt"]
    assert "clarification_answers" not in calls[4]["prompt"]
    if two_families:
        assert [call["agent"] for call in calls] == [
            "codex",
            "codex",
            "claude",
            "claude",
            "codex",
            "codex",
        ]
    report = request.versions.get().evidence
    assert report["database"]["status"] == "not_configured"
    assert not report["blocking"]
    for artifact in request.versions.get().artifacts.all():
        assert "Checked conclusions and limits" in artifact.content
        assert "Real records were not checked" in artifact.content
        assert repository["commit"] in artifact.content


def test_universal_statement_and_omitted_material_claim_cannot_be_certified(
    environment, storage, repository, bundle
):
    request = start(environment)
    unverified = verification(
        repository,
        claims=[
            claim(
                repository,
                id="analyst:active",
                universal=True,
                statement="Every export always excludes inactive rows.",
            )
        ],
    )
    execute(request, storage, outputs(repository, bundle, verified=unverified))
    assert request.status == "PARTIAL", request.error
    report = request.versions.get().evidence
    assert report["blocking"]
    assert report["claims"][0]["status"] == "partial"
    assert any(
        item["id"] == "counter:active" and item["status"] == "unverified"
        for item in report["claims"]
    )


def test_missing_verifier_role_waits_instead_of_publishing_self_approval(
    environment, storage, repository, bundle
):
    AIConnection.objects.filter(pk=1).update(roles=["analyst", "counter_analyst"])
    request = start(environment)
    calls, job = execute(request, storage, outputs(repository, bundle)[:4])
    assert len(calls) == 4
    assert job.status == "QUEUED" and request.status == "QUEUED"
    assert not request.versions.exists()
    assert request.analysis_runs.get().orchestration["waiting_role"] == "verifier"
    assert claim_job() is None


def test_no_finite_sql_observation_can_establish_universal_validity(
    environment, storage, repository, bundle
):
    from core.models import DatabaseConnection
    from core.secrets import encrypt

    database = DatabaseConnection.objects.create(
        name="Fixture records",
        host="db.invalid",
        database="fixture",
        username="reader",
        secret=encrypt("synthetic-v23-read-only"),
    )
    environment.database = database
    environment.save()
    request = start(environment)
    report = verification(repository)
    for item in report["report"]["claims"]:
        item.update(universal=True, sources=[{"kind": "sql", "query_id": "invented-query"}])
    calls, _ = execute(request, storage, outputs(repository, bundle, verified=report))
    assert request.status == "PARTIAL", request.error
    assert all("synthetic-v23-read-only" not in call["prompt"] for call in calls)
    assert calls[4]["database"] and calls[5]["database"] is None
    evidence = request.versions.get().evidence
    assert evidence["database"]["status"] == "not_checked"
    assert all(item["status"] == "unverified" for item in evidence["claims"])


def test_material_contradiction_performs_focused_check_then_independent_verification(
    environment, storage, repository, bundle
):
    request = start(environment)
    values = outputs(repository, bundle)
    values[3] = {
        "status": "NEEDS_VERIFICATION",
        "summary": "Check historical configuration.",
        "issues": ["A historical import appears inconsistent."],
        "verification": {
            "target": "code",
            "questions": ["Does current configuration permit inactive exports?"],
        },
    }
    values.insert(
        4,
        {
            "answers": [
                {
                    "question": "Does current configuration permit inactive exports?",
                    "answer": "Only the inspected filter is established.",
                    "evidence": ["export.py:selected"],
                }
            ],
            "remaining_uncertainties": ["Historical imports were not executed."],
        },
    )
    calls, _ = execute(request, storage, values)
    assert len(calls) == 7 and calls[-2]["public_role"] == "verifier"
    assert request.status == "PARTIAL", request.error
    assert "Historical imports were not executed." in request.versions.get().evidence["limitations"]


def test_current_configuration_never_allows_independent_review_to_be_disabled(client):
    from core.orchestration_settings import GlobalOrchestrationIn

    config = get_config()
    assert config["verifier_enabled"] and config["allow_confrontation"]
    assert config["reliability_protocol"] == "2.4"
    config = {
        key: value for key, value in config.items() if key in GlobalOrchestrationIn.model_fields
    }
    assert (
        client.put(
            "/api/orchestration-settings",
            json.dumps({**config, "verifier_enabled": False}),
            content_type="application/json",
        ).status_code
        == 422
    )


@pytest.mark.parametrize("workflow", ["request", "question"])
def test_historical_v23_resume_preserves_human_decision(
    environment, storage, repository, bundle, workflow
):
    request = Request.objects.create(
        environment=environment,
        workflow=workflow,
        need="Explain the export scope.",
        language="en",
    )
    assert request.analysis_protocol == "legacy"
    from core.services import enqueue_analysis

    enqueue_analysis(request.pk)
    question = {"id": "scope", "question": "Which rows should be included?"}
    execute(
        request,
        storage,
        [{**requirement(), "status": "NEEDS_CLARIFICATION", "questions": [question]}],
    )
    assert request.status == "NEEDS_CLARIFICATION"
    # Historical engine compatibility is a service contract, not the current public route.
    resumed = enqueue_analysis(
        request.pk,
        answers={"scope": "Include only active rows."},
        expected_decision_revision=0,
        analysis_protocol="2.3",
    )
    assert resumed.analysis_protocol == "2.3"
    calls, job = execute(request, storage, outputs(repository, bundle, workflow))
    assert job.status == "DONE" and request.status == "READY", request.error
    assert len(calls) == 6
    assert all("Include only active rows." in call["prompt"] for call in calls)
    assert request.versions.get().decisions_snapshot[0]["value"] == "Include only active rows."
