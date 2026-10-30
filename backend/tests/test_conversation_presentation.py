"""Conversation projections preserve attribution without exposing private orchestration."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.agent import Question
from core.analysis_flow import Orchestrator
from core.conversation import attribute_messages, role_reviews
from core.models import AnalysisRun, Request, RequestMessage

pytestmark = pytest.mark.django_db


def test_public_review_uses_only_recorded_report_fields(client, environment):
    request = Request.objects.create(environment=environment, need="Explain date validation.")
    AnalysisRun.objects.create(request=request, number=1, orchestration={
        "private_prompt": "Do not publish this prompt",
        "outputs": {
            "analyst": {"current_behavior": "Dates are checked when saving.", "private_reasoning": "Private notes", "claims": [{"statement": "Dates are ordered.", "status": "unverified", "sources": []}]},
            "counter_independent": {"current_behavior": "Imported records follow a separate path."},
            "comparison": {"summary": "Check imported records.", "issues": ["Import validation is unverified."]},
            "verifier": {"report": {"claims": [{"statement": "The import exception is unresolved.", "status": "partial"}], "limitations": ["No database was inspected."]}},
        },
    })
    response = client.get(f"/api/analyses/{request.pk}")
    assert response.status_code == 200
    run = response.json()["analysis_runs"][0]
    assert "orchestration" not in run
    assert "Private notes" not in response.content.decode()
    assert "Do not publish this prompt" not in response.content.decode()
    assert [review["public_role"] for review in run["role_reviews"]] == ["analyst", "counter_analyst", "counter_analyst", "verifier"]
    assert run["role_reviews"][2]["issues"] == ["Import validation is unverified."]
    assert run["role_reviews"][3]["limits"] == ["No database was inspected."]


def test_missing_reports_do_not_fabricate_agent_exchanges():
    assert role_reviews({"steps": [{"public_role": "analyst", "status": "DONE"}]}) == []


def historical_run():
    first = {"id": "screen", "question": "Which screen is affected?"}
    second = {"id": "dates", "question": "Which dates are shown?"}
    steps = [
        {"roles": ["requirement"], "public_role": "analyst", "provider": "codex", "connection_name": "Old ChatGPT", "model": "old-model", "status": "DONE", "started_at": "2026-10-26T00:29:19Z", "finished_at": "2026-10-26T00:30:36Z", "context_id": "first-context"},
        {"roles": ["requirement"], "public_role": "analyst", "provider": "antigravity", "connection_name": "Old Antigravity", "status": "DONE", "started_at": "2026-10-26T14:09:39Z", "finished_at": "2026-10-26T14:10:28Z", "context_id": "second-context"},
    ]
    run = {"number": 1, "steps": steps, "orchestration": {"structured_outputs": [
        {"roles": ["requirement"], "public_role": "analyst", "output": {"questions": [{**first, "kind": "free", "options": []}]}},
        {"roles": ["requirement"], "public_role": "analyst", "output": {"questions": [second]}},
    ]}}
    messages = [
        {"id": 1, "role": "user", "kind": "need", "content": "Explain dates.", "created_at": "2026-10-26T00:29:14Z"},
        {"id": 2, "role": "assistant", "kind": "clarification", "data": {"questions": [first]}, "created_at": "2026-10-26T00:30:36.050Z"},
        {"id": 3, "role": "user", "kind": "answer", "created_at": "2026-10-26T14:09:35Z"},
        {"id": 4, "role": "assistant", "kind": "clarification", "data": {"questions": [second]}, "created_at": "2026-10-26T14:10:28.050Z"},
    ]
    return run, messages


def test_historical_questions_bind_to_their_actual_step_even_when_provider_changes():
    run, messages = historical_run()
    attribute_messages(messages, [run])
    assert messages[1]["attribution"]["provider"] == "codex"
    assert messages[1]["attribution"]["context_id"] == "first-context"
    assert messages[3]["attribution"]["provider"] == "antigravity"
    assert messages[3]["attribution"]["public_role"] == "analyst"
    assert messages[1]["data"] == {"questions": [{"id": "screen", "question": "Which screen is affected?"}]}


@pytest.mark.parametrize("invalid", ["question_text", "question_id", "missing_report", "wrong_step", "after_message", "before_answer", "ambiguous_runs"])
def test_incomplete_or_ambiguous_history_does_not_invent_an_author(invalid):
    import copy

    run, messages = historical_run()
    runs = [run]
    if invalid == "question_text":
        messages[3]["data"]["questions"][0] = {"id": "dates", "question": "A different question"}
    elif invalid == "question_id":
        messages[3]["data"]["questions"][0] = {"id": "other", "question": "Which dates are shown?"}
    elif invalid == "missing_report":
        run["orchestration"]["structured_outputs"].pop()
    elif invalid == "wrong_step":
        run["steps"][1]["roles"] = ["independent"]
    elif invalid == "after_message":
        run["steps"][1]["finished_at"] = "2026-10-26T14:11:00Z"
    elif invalid == "before_answer":
        run["steps"][1]["started_at"] = "2026-10-26T14:08:00Z"
    else:
        other = copy.deepcopy(run)
        other["number"] = 2
        runs.append(other)
    attribute_messages(messages, runs)
    assert "attribution" not in messages[3]


def test_api_recovers_historical_authors_without_rewriting_saved_messages(client, environment):
    run, messages = historical_run()
    request = Request.objects.create(environment=environment, need="Explain historical dates.")
    AnalysisRun.objects.create(request=request, number=1, steps=run["steps"], orchestration=run["orchestration"])
    row = RequestMessage.objects.create(request=request, role="assistant", kind="clarification", content="Which screen is affected?", data=messages[1]["data"])
    RequestMessage.objects.filter(pk=row.pk).update(created_at=messages[1]["created_at"])
    response = client.get(f"/api/analyses/{request.pk}")
    assert response.status_code == 200
    assert response.json()["messages"][0]["attribution"]["connection_name"] == "Old ChatGPT"
    row.refresh_from_db()
    assert row.data == messages[1]["data"] and row.content == "Which screen is affected?"


@pytest.mark.parametrize("role", ["analyst", "counter_analyst", "verifier"])
def test_clarification_records_actual_role_and_preserves_the_pending_question(environment, role):
    request = Request.objects.create(environment=environment, need="Explain date validation.")
    run = AnalysisRun.objects.create(request=request, number=1)
    engine = SimpleNamespace(request=request, run=run, public_role=role,
                             persist_request=Mock(), persist_run=Mock(), on_progress=Mock())
    Orchestrator.clarify(engine, "Identify the affected screen.", [Question(id="screen", question="Which screen is affected?")])
    message = request.messages.get()
    assert message.data["public_role"] == role
    assert message.data["run_number"] == 1
    assert message.data["questions"] == request.questions
    assert run.status == "NEEDS_CLARIFICATION"
