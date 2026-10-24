"""Both analysis intents share scheduling, isolation, clarification and version boundaries."""

import copy
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import Client

from core.models import (
    AnalysisResult,
    DatabaseConnection,
    InstanceSettings,
    Job,
    QuestionDocument,
    Request,
)
from core.question_actions import create_request
from core.secrets import encrypt
from core.services import continue_conversation, enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def question(environment, storage):
    source = storage / "company/backend/contracts/export.py"
    source.parent.mkdir(parents=True)
    source.write_text("def export_active(rows):\n    return [r for r in rows if r.active]\n")
    return Request.objects.create(
        workflow="question",
        environment=environment,
        need="How are active exports selected?",
        language="en",
    )


@pytest.fixture
def explanation():
    return {
        "status": "READY",
        "answer": {
            "title": "Active export selection",
            "summary": "The existing function selects active rows.",
            "business_explanation": "Closed contracts do not appear in the export.",
            "technical_explanation": "export_active applies an active filter.",
            "verified_facts": ["The selection checks row.active."],
            "inferences": ["Other callers may share this filter."],
            "uncertainties": ["Scheduled usage was not executed."],
            "references": [
                {
                    "repository": "company/backend",
                    "path": "contracts/export.py",
                    "symbol": "export_active",
                }
            ],
        },
    }


def assessment(complexity="simple"):
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Understand active export selection",
        "questions": [],
        "ticket": None,
        "complexity": complexity,
    }


def report(**extra):
    return {
        "observed_behavior": "export_active filters by the active flag.",
        "evidence": ["contracts/export.py: export_active"],
        "verified_facts": ["Only active rows are selected."],
        "inferences": [],
        "uncertainties": [],
        "questions": [],
        **extra,
    }


def approved():
    return {"status": "APPROVED", "summary": "Evidence checked", "issues": [], "verification": None}


def execute(question, storage, values):
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(payload)
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return {"session_id": payload["session_id"] or str(uuid.uuid4()), "output": value}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        for _ in range(20 if question.analysis_protocol == "2.4" else 1):
            job = claim_job()
            assert job is not None
            perform_job(job)
            question.refresh_from_db()
            if question.status in {"READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"}:
                break
    question.refresh_from_db()
    return calls


def test_question_uses_existing_queue_without_ticket_goal_or_external_publication(
    question, storage, explanation
):
    enqueue_analysis(question.pk)
    job = Job.objects.get(target=str(question.pk))
    assert job.kind == "analysis"
    queue = Client().get("/api/queue").json()
    assert queue[0]["workflow"] == "question" and queue[0]["href"] == f"/questions/{question.pk}"
    calls = execute(
        question, storage, [assessment(), {"analysis": report(), "result": explanation}]
    )
    assert question.status == "READY", question.error
    assert [call["schema"]["title"] for call in calls] == [
        "RequirementAssessment",
        "QuestionCodeAndResult",
    ]
    assert all("INTENT: PROJECT QUESTION" in call["prompt"] for call in calls)
    version = question.versions.get()
    assert version.ticket == {} and version.explanation["title"] == "Active export selection"
    assert set(version.artifacts.values_list("name", flat=True)) == {"answer.md"}
    assert not AnalysisResult.objects.filter(request=question).exists()
    assert not QuestionDocument.objects.exists()
    assert not question.published_tickets.exists()
    data = Client().get(f"/api/questions/{question.pk}").json()
    assert "ticket" not in data and "goal_markdown" not in data["latest_version"]
    assert "a" * 40 in data["latest_version"]["answer_markdown"]
    assert "contracts/export.py" in data["latest_version"]["answer_markdown"]
    assert Client().get(f"/api/requests/{question.pk}").status_code == 404


def test_clarification_during_exploration_releases_worker_and_resumes_useful_history(
    question, storage, explanation
):
    enqueue_analysis(question.pk)
    first = execute(
        question,
        storage,
        [
            assessment(),
            {
                "analysis": report(
                    questions=[{"id": "scope", "question": "Scheduled or manual exports?"}]
                ),
                "result": None,
            },
        ],
    )
    assert question.status == "NEEDS_CLARIFICATION"
    assert not question.versions.exists()
    assert Job.objects.get(target=str(question.pk)).status == "DONE"
    assert claim_job() is None
    enqueue_analysis(question.pk, {"scope": "Manual exports only"})
    second = execute(
        question, storage, [assessment(), {"analysis": report(), "result": explanation}]
    )
    assert question.status == "READY", question.error
    assert all(call["session_id"] == question.session.runtime_id for call in second)
    assert first[0]["context_id"] == second[0]["context_id"]
    assert "Manual exports only" in second[-1]["prompt"]
    first_markdown = question.versions.get(number=1).artifacts.get(name="answer.md").content
    continue_conversation(question.pk, "Explain the ordering too", 1)
    updated = copy.deepcopy(explanation)
    updated["answer"]["summary"] = "The filter preserves input order."
    resumed = execute(question, storage, [assessment(), {"analysis": report(), "result": updated}])
    assert "Explain the ordering too" in resumed[-1]["prompt"]
    assert "The existing function selects active rows." in resumed[-1]["prompt"]
    assert question.versions.count() == 2
    assert question.versions.get(number=1).artifacts.get(name="answer.md").content == first_markdown
    old = Client().get(f"/api/questions/{question.pk}/versions/1").json()
    assert old["answer_markdown"] == first_markdown


@pytest.mark.parametrize("two_providers", [False, True])
def test_question_confrontation_uses_same_public_roles_and_independent_first_reports(
    question, storage, explanation, two_providers
):
    if two_providers:
        from core.models import AIConnection
        from core.providers import identity_for

        connection = AIConnection.objects.create(
            agent="claude", status="CONNECTED", availability="AVAILABLE"
        )
        identity_for(connection)
    question.confrontation = True
    question.save()
    enqueue_analysis(question.pk)
    calls = execute(
        question,
        storage,
        [
            assessment(),
            report(inferences=["PRIVATE_FIRST_CONCLUSION"]),
            report(),
            approved(),
            {"agreements": ["Active selection"], "divergences": [], "result": explanation},
        ],
    )
    assert question.status == "READY", question.error
    assert [call["profile"] for call in calls] == [
        "requirement",
        "code",
        "independent",
        "reviewer_writer",
        "synthesis",
    ]
    assert len({call["context_id"] for call in calls}) == 3
    assert "PRIVATE_FIRST_CONCLUSION" not in calls[2]["prompt"]
    assert "PRIVATE_FIRST_CONCLUSION" in calls[3]["prompt"]
    run = question.analysis_runs.get()
    assert set(run.orchestration["outputs"]) == {
        "requirement",
        "analyst",
        "counter_independent",
        "comparison",
        "verifier",
    }
    assert len({step["model_family"] for step in run.steps}) == (2 if two_providers else 1)


def test_question_code_report_clarification_also_works_in_standard_and_counter_paths(
    question, storage, explanation
):
    question.confrontation = True
    question.save()
    enqueue_analysis(question.pk)
    execute(
        question,
        storage,
        [assessment(), report(), report(questions=[{"id": "module", "question": "Which module?"}])],
    )
    assert question.status == "NEEDS_CLARIFICATION" and not question.versions.exists()
    assert Job.objects.get(target=str(question.pk)).status == "DONE"


def test_optional_database_stays_technical_and_focused_unknowns_cannot_disappear(
    question, storage, explanation
):
    database = DatabaseConnection.objects.create(
        name="Business fixture",
        host="db.invalid",
        database="business",
        username="reader",
        secret=encrypt("fixture-question-password"),
    )
    question.environment.database = database
    question.environment.save(update_fields=["database"])
    enqueue_analysis(question.pk)
    review = {
        "status": "NEEDS_VERIFICATION",
        "summary": "Check filtering",
        "issues": [],
        "verification": {"target": "code", "questions": ["Is access scoped?"]},
    }
    calls = execute(
        question,
        storage,
        [
            assessment("standard"),
            report(),
            {"review": review, "result": None},
            {
                "answers": [
                    {
                        "question": "Is access scoped?",
                        "answer": "Unknown",
                        "evidence": ["contracts/export.py"],
                    }
                ],
                "remaining_uncertainties": ["Access scoping remains unverified."],
            },
            explanation,
        ],
    )
    assert question.status == "PARTIAL", question.error
    assert (
        "Access scoping remains unverified."
        in question.versions.get().artifacts.get(name="answer.md").content
    )
    assert calls[0]["database"] is None
    assert all("fixture-question-password" not in call["prompt"] for call in calls)
    assert calls[1]["database"]["password"] == "fixture-question-password"
    assert "default_transaction_read_only=on" in calls[1]["database"]["options"]
    # The shared completion boundary preserves explicit unknowns even if the writer omits them.
    assert "Access scoping remains unverified." in calls[-1]["prompt"]


def test_unavailable_reference_path_is_repaired_once_before_publication(
    question, storage, explanation
):
    enqueue_analysis(question.pk)
    invalid = copy.deepcopy(explanation)
    invalid["answer"]["references"][0]["path"] = "missing.py"
    calls = execute(
        question,
        storage,
        [
            assessment(),
            {"analysis": report(), "result": invalid},
            {"analysis": report(), "result": explanation},
        ],
    )
    assert question.status == "READY" and len(calls) == 3
    assert "FORMAT CORRECTION" in calls[-1]["prompt"]
    enum = calls[-1]["schema"]["$defs"]["QuestionReference"]["properties"]["repository"]["enum"]
    assert enum == ["company/backend"]


def test_derived_request_uses_current_baseline_and_runs_independent_ticket_pipeline(
    question, storage, explanation, bundle, code_report
):
    enqueue_analysis(question.pk)
    execute(question, storage, [assessment(), {"analysis": report(), "result": explanation}])
    original = question.versions.get()
    # A new derived request adopts mandatory review even with a legacy disabled policy.
    InstanceSettings.objects.update_or_create(pk=1, defaults={"allow_confrontation": False})
    request = create_request(
        question.pk, 1, question.environment_id, "Add an option for archived exports."
    )
    transferred = Path(request.attachments.get().path).read_bytes()
    from core.git import run as git

    repository = storage / "company/backend"
    git("init", repository)
    git("-C", repository, "add", "contracts/export.py")
    git(
        "-C",
        repository,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    sha = git("-C", repository, "rev-parse", "HEAD")
    question.environment.repositories.update(sha=sha)
    enqueue_analysis(request.pk)
    claim = {
        "id": "active",
        "statement": "The inspected export selects active rows.",
        "kind": "observed",
        "status": "supported",
        "scope": {
            "environment": "Staging",
            "period": "Frozen source version",
            "conditions": ["export_active is called"],
            "population": "Input rows",
            "sample_limits": "Only this function was inspected",
        },
        "sources": [
            {
                "kind": "git",
                "repository": "company/backend",
                "commit": sha,
                "path": "contracts/export.py",
                "line_start": 1,
                "line_end": 2,
                "excerpt": (repository / "contracts/export.py").read_text().strip(),
            }
        ],
    }
    verified = [{**claim, "id": role + ":active"} for role in ("analyst", "counter")]
    # The transferred attachment is inspected before the three independent roles finish.
    calls = execute(
        request,
        storage,
        [
            assessment("standard"),
            {"observations": [], "questions": []},
            {
                **code_report,
                "claims": [claim],
                "coverage": {
                    "inspected_areas": ["Export filter"],
                    "new_elements": [],
                    "unexplored_zones": [],
                },
            },
            {
                **code_report,
                "claims": [claim],
                "coverage": {
                    "inspected_areas": ["Export filter and caller scope"],
                    "new_elements": [],
                    "unexplored_zones": [],
                },
            },
            approved(),
            {
                "report": {"claims": verified},
                "questions": [],
                "coverage_resolutions": [],
                "additional_omissions": [],
            },
            bundle.model_dump(),
        ],
    )
    assert request.status == "READY", request.error
    assert request.analysis_protocol == "2.4" and len(calls) == 7
    assert request.baseline[0]["sha"] == sha
    assert original.baseline[0]["sha"] == "a" * 40
    assert all("TRANSFERRED QUESTION CONTEXT" in call["prompt"] for call in calls)
    assert all(transferred.decode() not in call["prompt"] for call in calls)
    assert "verification_required" in calls[1]["prompt"]
    assert request.session.context_id != question.session.context_id
    assert request.versions.get().explanation == {}
    assert set(request.versions.get().artifacts.values_list("name", flat=True)) == {
        "ticket.md",
        "goal.md",
    }
    assert request.source_question_version_id == original.pk
    # Changing the question answer later cannot rewrite the already transferred file.
    continue_conversation(question.pk, "Explain scheduling too", 1)
    execute(question, storage, [assessment(), {"analysis": report(), "result": explanation}])
    assert Path(request.attachments.get().path).read_bytes() == transferred
    assert request.source_question_version_id == original.pk
