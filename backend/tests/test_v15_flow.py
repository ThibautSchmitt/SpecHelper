import uuid
from unittest.mock import patch

import pytest

from core.agent import ProviderUnavailable
from core.models import AIConnection, InstanceSettings, Job, Request
from core.orchestration_settings import get_config
from core.providers import identity_for
from core.services import enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


def assessment():
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Export active records",
        "questions": [],
        "ticket": None,
        "complexity": "standard",
    }


def review(verification=None):
    return {
        "status": "NEEDS_VERIFICATION" if verification else "APPROVED",
        "summary": "Evidence checked",
        "issues": [],
        "verification": verification,
    }


def connected(agent="claude", **kwargs):
    item = AIConnection.objects.create(
        agent=agent, status="CONNECTED", availability="AVAILABLE", **kwargs
    )
    identity_for(item)
    return item


def run_job(job, storage, outputs):
    def invoke(_path, payload, **kwargs):
        value = outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return {"session_id": payload["session_id"] or str(uuid.uuid4()), "output": value}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke) as runtime,
    ):
        perform_job(job)
    return runtime


def outputs(code_report, bundle, verifier=True):
    final = (
        {"agreements": ["Use existing export"], "divergences": [], "result": bundle.model_dump()}
        if verifier
        else bundle.model_dump()
    )
    return [
        assessment(),
        {**code_report, "uncertainties": ["ANALYST_PRIVATE_CONCLUSION"]},
        code_report,
        review(),
        final,
    ]


@pytest.mark.parametrize("two_families", [False, True])
def test_exact_pair_distinct_role_sessions_and_independent_counter_context(
    environment, storage, bundle, code_report, two_families
):
    if two_families:
        connected()
    request = Request.objects.create(
        environment=environment, need="Export active records", confrontation=True
    )
    enqueue_analysis(request.pk)
    runtime = run_job(claim_job(), storage, outputs(code_report, bundle))
    request.refresh_from_db()
    assert request.status == "READY"
    calls = [call.args[1] for call in runtime.call_args_list]
    assert [call["profile"] for call in calls] == [
        "requirement",
        "code",
        "independent",
        "reviewer_writer",
        "synthesis",
    ]
    assert len({call["context_id"] for call in calls}) == 3
    assert all(call["independent_context"] for call in calls)
    assert calls[0]["context_id"] == calls[1]["context_id"]
    assert calls[2]["context_id"] == calls[3]["context_id"]
    assert "ANALYST_PRIVATE_CONCLUSION" not in calls[2]["prompt"]
    assert "ANALYST_PRIVATE_CONCLUSION" in calls[3]["prompt"]
    run = request.analysis_runs.get()
    assert set(run.orchestration["sessions"]) == {"analyst", "counter_analyst", "verifier"}
    assert [assignment["role"] for assignment in run.orchestration["assignments"]] == [
        "analyst",
        "counter_analyst",
        "verifier",
    ]
    assert [step["model_family"] for step in run.steps] == (
        ["openai", "openai", "anthropic", "anthropic", "openai"] if two_families else ["openai"] * 5
    )
    assert bool(run.warnings) is not two_families


def test_availability_wait_preserves_checkpoints_and_resumes_without_duplicate_analysis(
    environment, storage, bundle, code_report
):
    config = get_config()
    config["allow_same_family_fallback"] = False
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    first = run_job(claim_job(), storage, [assessment(), code_report])
    assert first.call_count == 2
    request.refresh_from_db()
    job = Job.objects.get(target=str(request.pk))
    assert request.status == job.status == "QUEUED"
    assert request.analysis_runs.get().orchestration["waiting_role"] == "counter_analyst"
    assert claim_job() is None
    connected()
    second = run_job(
        claim_job(),
        storage,
        [
            code_report,
            review(),
            {"agreements": [], "divergences": [], "result": bundle.model_dump()},
        ],
    )
    assert [c.args[1]["profile"] for c in second.call_args_list] == [
        "independent",
        "reviewer_writer",
        "synthesis",
    ]
    request.refresh_from_db()
    assert request.status == "READY" and request.versions.count() == 1


def test_verifier_disabled_uses_only_pair_and_one_targeted_followup(
    environment, storage, bundle, code_report
):
    config = get_config()
    config["verifier_enabled"] = False
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    values = [
        assessment(),
        code_report,
        code_report,
        review({"target": "code", "questions": ["Does the filter exist?"]}),
        {
            "answers": [
                {
                    "question": "Does the filter exist?",
                    "answer": "No",
                    "evidence": ["export.py: filter"],
                }
            ],
            "remaining_uncertainties": [],
        },
        bundle.model_dump(),
    ]
    runtime = run_job(claim_job(), storage, values)
    calls = [c.args[1] for c in runtime.call_args_list]
    assert [c["profile"] for c in calls] == [
        "requirement",
        "code",
        "independent",
        "reviewer_writer",
        "code",
        "writer",
    ]
    assert len({c["context_id"] for c in calls}) == 2
    assert request.analysis_runs.get().orchestration["calls"] == 6


def test_quota_failure_reassigns_only_failed_stage_and_keeps_validated_counter_report(
    environment, storage, bundle, code_report
):
    connected()
    connected(agent="codex", name="Second account")
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    values = [
        assessment(),
        code_report,
        code_report,
        ProviderUnavailable("QUOTA_EXHAUSTED"),
        review(),
        {"agreements": [], "divergences": [], "result": bundle.model_dump()},
    ]
    runtime = run_job(claim_job(), storage, values)
    profiles = [c.args[1]["profile"] for c in runtime.call_args_list]
    assert profiles.count("code") == profiles.count("independent") == 1
    assert profiles.count("reviewer_writer") == 2
    request.refresh_from_db()
    assert request.status == "READY"
    assert any(w["code"] == "PROVIDER_FALLBACK" for w in request.analysis_runs.get().warnings)


def test_global_call_budget_is_durable_across_provider_waits(
    environment, storage, bundle, code_report
):
    config = get_config()
    config["max_calls"] = 2
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    runtime = run_job(claim_job(), storage, [assessment(), code_report])
    request.refresh_from_db()
    assert runtime.call_count == 2 and request.status == "ERROR"
    run = request.analysis_runs.get()
    assert run.orchestration["calls"] == 2
    assert set(run.orchestration["outputs"]) == {"requirement", "analyst"}
    assert request.versions.count() == 0


def test_role_selection_observes_availability_at_each_boundary(
    environment, storage, bundle, code_report
):
    unavailable = connected(roles=["counter_analyst", "verifier"])
    identity = identity_for(unavailable)
    identity.availability = "QUOTA_EXHAUSTED"
    identity.save(update_fields=["availability"])
    config = get_config()
    config["allow_same_family_fallback"] = False
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    values = outputs(code_report, bundle)

    def invoke(_path, payload, **kwargs):
        if payload["profile"] == "code":
            identity.availability = "AVAILABLE"
            identity.save(update_fields=["availability"])
        return {"session_id": payload["session_id"] or str(uuid.uuid4()), "output": values.pop(0)}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        perform_job(claim_job())
    run = request.analysis_runs.get()
    assert run.status == "READY"
    assert [a["agent"] for a in run.orchestration["assignments"]] == ["codex", "claude", "codex"]


def test_configuration_inheritance_and_explicit_skill_overrides_affect_actual_prompts(
    environment, storage, bundle, code_report
):
    from core.models import AgentProfile, SkillDefinition

    config = get_config()
    skill = SkillDefinition.objects.create(
        slug="explicit-skill",
        name="Explicit",
        instructions="EXPLICIT_SKILL_SENTINEL",
        enabled=False,
    )
    excluded = SkillDefinition.objects.create(
        slug="disabled-skill", name="Excluded", instructions="DISABLED_SKILL_SENTINEL"
    )
    profile = AgentProfile.objects.get(pk="reviewer")
    profile.instructions = "EXPLICIT_INTERNAL_AGENT_SENTINEL"
    profile.enabled = False
    profile.save(update_fields=["instructions", "enabled"])
    config["default_skills"] = [excluded.pk]
    config["role_instructions"]["counter_analyst"] = "GLOBAL_COUNTER_SENTINEL"
    config["active_internal_agents"] = ["requirement", "code", "writer", "reviewer"]
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    AIConnection.objects.filter(pk=1).update(
        additional_instructions="CONNECTION_SENTINEL",
        skill_overrides={skill.pk: True, excluded.pk: False},
    )
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    runtime = run_job(claim_job(), storage, outputs(code_report, bundle))
    calls = [c.args[1] for c in runtime.call_args_list]
    for call in calls:
        assert "CONNECTION_SENTINEL" in call["prompt"]
        assert "EXPLICIT_SKILL_SENTINEL" in call["prompt"]
        assert "DISABLED_SKILL_SENTINEL" not in call["prompt"]
        assert "read-only" in call["prompt"].lower()
    assert "GLOBAL_COUNTER_SENTINEL" not in calls[1]["prompt"]
    assert "GLOBAL_COUNTER_SENTINEL" in calls[2]["prompt"]
    assert "EXPLICIT_INTERNAL_AGENT_SENTINEL" in calls[3]["prompt"]


def test_clarification_keeps_validated_attachment_facts_and_starts_fresh_role_sessions(
    environment, storage, bundle, code_report
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.services import add_attachment

    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    add_attachment(request.pk, SimpleUploadedFile("rules.txt", b"Active records"))
    enqueue_analysis(request.pk)
    question = {"id": "scope", "question": "Which scope?"}
    runtime = run_job(
        claim_job(),
        storage,
        [
            assessment(),
            {
                "observations": [
                    {
                        "attachment": "rules.txt",
                        "facts": ["Validated attachment fact"],
                        "uncertainties": [],
                    }
                ],
                "questions": [question],
            },
        ],
    )
    request.refresh_from_db()
    assert request.status == "NEEDS_CLARIFICATION", request.error
    original = {c.args[1]["context_id"] for c in runtime.call_args_list}
    enqueue_analysis(request.pk, answers={"scope": "Active records only"})
    resumed = run_job(
        claim_job(),
        storage,
        [
            code_report,
            code_report,
            review(),
            {"agreements": [], "divergences": [], "result": bundle.model_dump()},
        ],
    )
    calls = [c.args[1] for c in resumed.call_args_list]
    assert [c["profile"] for c in calls] == ["code", "independent", "reviewer_writer", "synthesis"]
    assert not original.intersection(c["context_id"] for c in calls)
    assert "Validated attachment fact" in calls[0]["prompt"]
    assert "Active records only" in calls[0]["prompt"]
    assert request.analysis_runs.latest("number").status == "READY"


def test_waiting_does_not_reset_global_deadline_or_destroy_validated_outputs(
    environment, storage, bundle, code_report
):
    from datetime import timedelta

    from django.utils import timezone

    config = get_config()
    config["allow_same_family_fallback"] = False
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    run_job(claim_job(), storage, [assessment(), code_report])
    run = request.analysis_runs.get()
    run.orchestration["deadline_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    run.save(update_fields=["orchestration"])
    runtime = run_job(claim_job(), storage, [])
    run.refresh_from_db()
    assert runtime.call_count == 0 and run.status == "ERROR"
    assert set(run.orchestration["outputs"]) == {"requirement", "analyst"}


def test_counter_and_verifier_can_check_database_evidence_without_credentials_in_prompt(
    environment, storage, bundle, code_report
):
    from core.models import DatabaseConnection
    from core.secrets import encrypt

    database = DatabaseConnection.objects.create(
        name="Read-only fixture",
        host="database.invalid",
        database="business",
        username="reader",
        secret=encrypt("fixture-only-not-real-password"),
    )
    environment.database = database
    environment.save(update_fields=["database"])
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    runtime = run_job(claim_job(), storage, outputs(code_report, bundle))
    calls = [c.args[1] for c in runtime.call_args_list]
    assert calls[0]["database"] is None
    assert all(c["database"]["password"] == "fixture-only-not-real-password" for c in calls[1:])
    assert all("default_transaction_read_only=on" in c["database"]["options"] for c in calls[1:])
    assert all("fixture-only-not-real-password" not in c["prompt"] for c in calls)


@pytest.mark.parametrize("verifier_enabled", [False, True])
def test_unresolved_focused_check_cannot_be_erased_by_ready_final_artifacts(
    environment, storage, bundle, code_report, verifier_enabled
):
    config = get_config()
    config["verifier_enabled"] = verifier_enabled
    InstanceSettings.objects.filter(pk=1).update(orchestration=config)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    values = [
        assessment(),
        code_report,
        code_report,
        review({"target": "code", "questions": ["Are audit permissions defined?"]}),
        {
            "answers": [
                {
                    "question": "Are audit permissions defined?",
                    "answer": "Not established",
                    "evidence": ["export.py: permissions"],
                }
            ],
            "remaining_uncertainties": ["Audit export permissions remain unverified."],
        },
        {"agreements": [], "divergences": [], "result": bundle.model_dump()}
        if verifier_enabled
        else bundle.model_dump(),
    ]
    run_job(claim_job(), storage, values)
    request.refresh_from_db()
    assert request.status == "PARTIAL"
    result = request.versions.get()
    for name in ("ticket.md", "goal.md"):
        assert (
            "Audit export permissions remain unverified." in result.artifacts.get(name=name).content
        )


@pytest.mark.parametrize("full_ticket", [False, True])
def test_long_unresolved_checks_preserve_full_goal_without_invalid_ticket_output(
    environment, storage, bundle, code_report, full_ticket
):
    from core.artifacts import ArtifactOutput

    result = bundle.model_dump()
    result["ticket"]["risks"] = [f"Original risk {index}" for index in range(8)]
    result["goal"]["constraints"] = [f"Original constraint {index}" for index in range(20)]
    if full_ticket:
        result["ticket"]["context"] = "context " * 210
        result["ticket"]["need"] = "need " * 210
        result["ticket"]["proposed_solution"] = "solution " * 210
    ArtifactOutput.model_validate(result)
    unresolved = [f"Unresolved issue {index}: " + "verification " * 200 for index in range(8)]
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    values = [
        assessment(),
        code_report,
        code_report,
        review({"target": "code", "questions": ["Are audit permissions defined?"]}),
        {
            "answers": [
                {
                    "question": "Are audit permissions defined?",
                    "answer": "Not established",
                    "evidence": ["export.py: permissions"],
                }
            ],
            "remaining_uncertainties": unresolved,
        },
        {"agreements": [], "divergences": [], "result": result},
    ]
    run_job(claim_job(), storage, values)
    request.refresh_from_db()
    run = request.analysis_runs.get()
    assert "focused_verification" in run.orchestration["outputs"]
    if full_ticket:
        assert request.status == "ERROR" and not request.versions.exists()
        assert "could not retain unresolved checks within the ticket format" in request.error
    else:
        assert request.status == "PARTIAL"
        version = request.versions.get()
        assert len(version.ticket["risks"]) <= 8
        goal = version.artifacts.get(name="goal.md").content
        for issue in unresolved:
            assert issue in goal
        assert "Original risk 7" in goal and "Original constraint 19" in goal
