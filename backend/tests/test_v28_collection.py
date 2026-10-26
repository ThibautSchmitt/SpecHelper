"""Application measurements must belong to the frozen case, not a substituted run."""

from datetime import timedelta

import pytest
from django.utils import timezone
from scripts.qualification.collect import collect_request, observed_attempts, validate_request

from core.models import AnalysisRun, Request, ResultVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(environment):
    request = Request.objects.create(
        need="Explain the SQL query.", workflow="question", language="en",
        environment=environment, status="READY",
        baseline=[{"repository": "company/backend", "sha": "a" * 40}],
    )
    packet = {
        "case_id": "Q01", "need": request.need, "workflow": "question", "language": "en",
        "repositories": [{"id": "backend", "git_sha": "a" * 40}],
        "database": {"state": "absent"}, "attachments": [],
    }
    return request, packet


def test_collection_rejects_stale_source_or_another_need_instead_of_attributing_its_result(case):
    request, packet = case
    validate_request(packet, request)
    request.baseline[0]["sha"] = "b" * 40
    with pytest.raises(ValueError, match="baseline"):
        validate_request(packet, request)
    request.baseline[0]["sha"] = "a" * 40
    request.need = "Another need"
    with pytest.raises(ValueError, match="frozen case"):
        validate_request(packet, request)


def test_collection_rejects_missing_frozen_attachment_and_different_database_availability(case):
    request, packet = case
    packet["attachments"] = [{"sha256": "expected-attachment"}]
    with pytest.raises(ValueError, match="attachments"):
        validate_request(packet, request)
    packet["attachments"] = []
    request.database_snapshot = {"id": 1, "name": "A different database"}
    with pytest.raises(ValueError, match="database availability"):
        validate_request(packet, request)


def test_failed_required_stage_is_collected_as_partial_with_actual_usage_and_duration(case):
    request, packet = case
    request.status = "ERROR"
    request.error = "A required tool was refused."
    started = timezone.now()
    AnalysisRun.objects.create(
        request=request, number=1, status="ERROR", started_at=started,
        finished_at=started + timedelta(seconds=5),
        steps=[{
            "attempts": 1, "public_role": "counter_analyst", "provider": "antigravity",
            "model": "fixture-gemini", "model_family": "google", "context_id": "fresh-context",
            "status": "ERROR", "failure": "PERMISSION_DENIED", "usage": {"total_tokens": 42},
        }],
    )
    observation = collect_request(packet, request, {"packet_sha256": "frozen-packet"},
                                  {"instructions": {}}, {"antigravity": {
                                      "version": "fixture-cli", "observed_at": started.isoformat(),
                                      "source": "fixture --version",
                                  }})
    assert observation["status"] == "PARTIAL"
    assert observation["application_status"] == "ERROR"
    assert observation["output"]["result"] is None
    assert observation["attempts"][0]["usage"] == {"total_tokens": 42}
    assert observation["elapsed_seconds"] == 5


def test_missing_cli_observation_cannot_be_filled_from_the_expected_protocol():
    with pytest.raises(ValueError, match="actual CLI"):
        observed_attempts([{"attempts": 1, "provider": "codex"}], {})


def test_changed_frozen_instructions_invalidate_the_comparison(case):
    request, packet = case
    started = timezone.now()
    run = AnalysisRun.objects.create(
        request=request, number=1, status="READY", started_at=started,
        finished_at=started + timedelta(seconds=1),
        orchestration={"config": {"global_instructions": "Different instructions"}},
    )
    ResultVersion.objects.create(request=request, run=run, number=1, environment_name="Fixture")
    with pytest.raises(ValueError, match="orchestration settings"):
        collect_request(packet, request, {"packet_sha256": "frozen"}, {
            "instructions": {"application_config": {"global_instructions": "Frozen instructions"}},
        }, {})


def test_interrupted_run_uses_its_persisted_step_end_without_inventing_a_completion(case):
    request, packet = case
    request.status = "ERROR"
    started = timezone.now()
    AnalysisRun.objects.create(
        request=request, number=1, status="ERROR", started_at=started,
        steps=[{
            "attempts": 1, "public_role": "analyst", "provider": "codex",
            "status": "ERROR", "context_id": "fixture-context", "model": "fixture-gpt",
            "model_family": "openai", "started_at": started.isoformat(),
            "finished_at": (started + timedelta(seconds=7)).isoformat(),
        }],
    )
    result = collect_request(packet, request, {"packet_sha256": "frozen"}, {"instructions": {}}, {
        "codex": {"version": "fixture", "observed_at": started.isoformat(), "source": "fixture --version"},
    })
    assert result["status"] == "PARTIAL"
    assert result["elapsed_seconds"] == result["execution_seconds"] == 7
    assert result["finished_at_source"] == "last_persisted_step"


def test_gate_clarification_is_measured_without_a_job_or_a_frozen_analysis_baseline(case):
    request, packet = case
    request.status, request.baseline = "DRAFT", []
    request.scope_assessment = {
        "status": "NEEDS_CLARIFICATION", "context_revision": request.environment.context_revision,
        "assessed_at": (request.created_at + timedelta(milliseconds=2)).isoformat(),
    }
    result = collect_request(packet, request, {"packet_sha256": "frozen"}, {"instructions": {}}, {})
    assert result["status"] == "PARTIAL" and result["scope_status"] == "NEEDS_CLARIFICATION"
    assert result["elapsed_seconds"] == 0.002 and result["execution_seconds"] == 0
    assert result["attempts"] == [] and result["output"]["result"] is None
