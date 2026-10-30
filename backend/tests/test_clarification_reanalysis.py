"""Human revisions invalidate old completion fences while retaining recorded evidence."""

from types import SimpleNamespace

import pytest
from test_analysis_progress import start

from core.analysis_flow import Orchestrator, RepeatedBusinessQuestion, Review, context
from core.models import BusinessDecision, RequestMessage, StepExecution
from core.services import resume_clarification
from core.step_execution import StepYield, complete_invocation, retry_analysis, wait_or_retry
from core.worker import claim_job

pytestmark = pytest.mark.django_db


def test_replaced_answer_invalidates_old_completions_and_freezes_latest_revision(environment):
    value, job = start(environment)
    question={"id":"scope", "question":"Explain the selected scope?"}
    previous=BusinessDecision.objects.create(request=value, sequence=1, revision=1, key="scope", question=question, value="First scope")
    BusinessDecision.objects.create(request=value, sequence=2, revision=2, key="scope", question=question, value="Explain current behavior only", previous=previous)
    value.decision_revision, value.status = 2, "NEEDS_CLARIFICATION"
    value.save()
    run=job.analysis_run
    outputs={"requirement":{"understanding":"Old scope"}, "analyst":{"claims":[{"statement":"Recorded evidence"}]}, "verifier":{"questions":[question]}}
    run.orchestration.update(outputs=outputs, checkpoint="verifier", current_role="verifier", evidence={"old":"derived"})
    run.status="NEEDS_CLARIFICATION"
    run.save()
    job.status="DONE"
    job.payload["changed_decision_keys"]=["previous-scope"]
    job.save()
    job.executions.update(status="DONE")
    StepExecution.objects.create(job=job, checkpoint="analyst", public_role="analyst", status="DONE", output=outputs["analyst"])
    StepExecution.objects.create(job=job, checkpoint="verifier", public_role="verifier", status="DONE", output=outputs["verifier"])
    resume_clarification(value, run, ["scope"])
    run.refresh_from_db()
    job.refresh_from_db()
    assert run.orchestration["outputs"] == {}
    assert run.orchestration["clarification_history"][-1]["outputs"] == outputs
    assert "evidence" not in run.orchestration
    assert set(job.executions.values_list("status", flat=True)) == {"INVALIDATED"}
    assert run.context_snapshot["changed_decision_keys"] == ["scope"]
    assert run.context_snapshot["business_decisions"]["revision"] == 2
    assert job.payload["next_checkpoint"] == "requirement"


def test_retry_after_input_revision_does_not_treat_superseded_steps_as_a_loop(environment):
    value, job = start(environment)
    run = job.analysis_run
    run.orchestration["outputs"] = {"requirement":{"understanding":"The user wants current behavior only."}}
    run.save(update_fields=["orchestration"])
    old = StepExecution.objects.create(job=job, checkpoint="analyst", public_role="analyst", status="DONE", output={"evidence":["Previously recorded source observation"]})
    wait_or_retry(job, job.payload["attempt_id"], "Interrupted after a human revision", failed=True)
    retry_analysis(value.pk)
    old.refresh_from_db()
    assert old.status == "INVALIDATED"
    assert old.output["evidence"] == ["Previously recorded source observation"]
    claimed = claim_job()
    complete_invocation(claimed, claimed.payload["attempt_id"], StepYield("analyst", "analyst"))
    claimed.refresh_from_db()
    assert claimed.status == "QUEUED" and claimed.payload["next_checkpoint"] == "analyst"
    assert claim_job().executions.get(status="RUNNING").checkpoint == "analyst"


def test_latest_answer_is_exposed_separately_from_the_old_question(environment):
    value, job = start(environment)
    RequestMessage.objects.create(request=value, role="user", kind="answer", content="Should creation remain allowed?\nI only want to understand current behavior.", data={"answers":{"scope":"I only want to understand current behavior."}})
    data = context(value, job.analysis_run)
    assert data["latest_user_message"] == "I only want to understand current behavior."
    assert data["recent_messages"][-1]["content"].startswith("Should creation remain allowed?")


def test_repeated_question_cannot_bypass_answer_history_with_a_different_id(environment):
    value, _ = start(environment)
    value.workflow = "question"
    value.conversation = [{"questions":[{"id":"old", "question":"Should creation remain allowed?"}], "answers":{"old":"Explain current behavior, without proposing a change."}}]
    owner = Orchestrator.__new__(Orchestrator)
    owner.request, owner.run, owner.is_question = value, SimpleNamespace(context_snapshot={}), True
    output = Review.model_validate({"status":"NEEDS_CLARIFICATION", "summary":"A question", "issues":[], "verification":None, "questions":[{"id":"new", "question":"SHOULD creation remain allowed?"}]})
    with pytest.raises(RepeatedBusinessQuestion):
        owner.validate_business_questions(output)


def test_factual_question_instructions_do_not_ask_for_future_policy():
    owner = Orchestrator.__new__(Orchestrator)
    owner.request = SimpleNamespace(intent_mode="explicit")
    owner.is_question = True
    text = owner.instruction_for_intent(Review, "Compare recorded evidence.")
    assert "latest_user_message" in text and "Never ask the user to approve" in text
