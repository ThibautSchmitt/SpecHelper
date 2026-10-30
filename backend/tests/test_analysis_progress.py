"""Progress, not total invocation count, controls checkpoint advancement."""

import copy
import uuid
from unittest.mock import patch

import pytest

from core.models import AnalysisRun, Request, StepExecution
from core.services import enqueue_analysis
from core.step_execution import NO_PROGRESS, StepYield, complete_invocation
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


def start(environment):
    request = Request.objects.create(environment=environment, analysis_protocol="2.4", need="Explain export conditions.")
    enqueue_analysis(request.pk)
    return request, claim_job()


def test_checkpoint_progress_continues_beyond_old_total_call_limit(environment, storage):
    request, job = start(environment)
    run = job.analysis_run
    run.orchestration["calls"] = 100
    run.orchestration["config"]["max_calls"] = 6
    run.save(update_fields=["orchestration"])
    output = {"status": "READY_TO_ANALYZE", "understanding": "Explain export conditions.", "questions": [], "ticket": None, "complexity": "simple"}
    with patch("core.worker.request_workspace", return_value=storage), patch("core.worker.runtime_call", return_value={"output": output, "session_id": str(uuid.uuid4())}) as caller:
        perform_job(job)
    job.refresh_from_db()
    run.refresh_from_db()
    assert caller.call_count == 1
    assert run.orchestration["calls"] == 101
    assert job.status == "QUEUED" and job.payload["next_checkpoint"] == "analyst"
    assert run.orchestration["outputs"]["requirement"]["understanding"] == output["understanding"]
    assert not request.versions.exists()


@pytest.mark.parametrize("fault", ["same_checkpoint", "cached_checkpoint", "completed_checkpoint", "missing_output", "missing_terminal_result"])
def test_repeated_or_empty_transitions_stop_without_losing_observations(environment, fault):
    request, job = start(environment)
    run = job.analysis_run
    run.orchestration["outputs"] = {"requirement": {"understanding": "Validated business facts"}}
    pending = StepYield("analyst", "analyst")
    if fault == "same_checkpoint":
        pending = StepYield("requirement", "analyst")
    elif fault == "cached_checkpoint":
        run.orchestration["outputs"]["analyst"] = {"evidence": ["Previously accepted evidence"]}
    elif fault == "completed_checkpoint":
        StepExecution.objects.create(job=job, checkpoint="analyst", public_role="analyst", status="DONE", output={"evidence": ["Retained audit evidence"]})
    elif fault == "missing_output":
        run.orchestration["outputs"] = {}
    elif fault == "missing_terminal_result":
        pending = None
    run.save(update_fields=["orchestration"])
    original = copy.deepcopy(run.orchestration["outputs"])
    baseline = copy.deepcopy(run.context_snapshot)
    complete_invocation(job, job.payload["attempt_id"], pending)
    job.refresh_from_db()
    request.refresh_from_db()
    run.refresh_from_db()
    assert job.status == request.status == "ERROR"
    assert job.error == NO_PROGRESS
    assert run.orchestration["outputs"] == original and run.context_snapshot == baseline
    assert not request.versions.exists()
    assert job.executions.get(checkpoint="requirement").status == "ERROR"


def test_cached_validated_output_can_resume_at_a_new_checkpoint(environment):
    _, job = start(environment)
    run = AnalysisRun.objects.get(job=job)
    run.orchestration["outputs"] = {"requirement": {"understanding": "Accepted before a worker restart"}}
    run.save(update_fields=["orchestration"])
    complete_invocation(job, job.payload["attempt_id"], StepYield("analyst", "analyst"))
    job.refresh_from_db()
    assert job.status == "QUEUED" and job.payload["next_checkpoint"] == "analyst"
