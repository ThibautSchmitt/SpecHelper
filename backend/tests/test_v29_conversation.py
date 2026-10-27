"""Two dependent human choices, repeated-question repair and late need revision."""

import copy
import uuid
from unittest.mock import patch

import pytest
from test_v22_decisions import question
from test_v24_omissions import committed_source as _committed_source
from test_v24_omissions import report, verification

from core.models import Request
from core.services import enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db
committed_source = _committed_source


def test_two_choices_and_late_edit_keep_answers_and_immutable_result(client, environment, storage, committed_source, bundle):
    value = Request.objects.create(environment=environment, need="Explain contract cancellation and export behavior.",
                                   intent_mode="auto", analysis_protocol="2.4")
    enqueue_analysis(value.pk)
    first = question()
    second = question(id="export-scope", decision_key="export-scope", question="Which contracts should the export include?")

    def requirement(questions):
        return {"status": "NEEDS_CLARIFICATION" if questions else "READY_TO_ANALYZE", "ticket": None,
                "understanding": "Explain the applicable contract rules.", "questions": questions,
                "complexity": "standard", "intent": "feature"}

    outputs = [requirement([first]), requirement([second]), requirement([second]), requirement([]),
               report(committed_source), report(committed_source, exception=True),
               {"status": "APPROVED", "summary": "Check the migration exception.", "issues": [], "verification": None},
               verification(committed_source), bundle.model_dump()]
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(copy.deepcopy(payload))
        assert outputs
        return {"output": outputs.pop(0), "session_id": payload["session_id"] or str(uuid.uuid4())}

    def process():
        for _ in range(16):
            job = claim_job()
            if not job:
                break
            perform_job(job)
            value.refresh_from_db()
            if value.status in {"READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"}:
                break

    with patch("core.worker.request_workspace", return_value=storage), patch("core.worker.runtime_call", side_effect=invoke):
        process()
        assert value.status == "NEEDS_CLARIFICATION", value.error
        for index, topic in enumerate(("termination", "export-scope")):
            response = client.post(f"/api/requests/{value.pk}/answers", {
                "choices": {topic: {"option_id": "a"} if index == 0 else {"option_id": "other", "text": "Only active contracts are exported."}},
                "expected_decision_revision": index,
            }, content_type="application/json")
            assert response.status_code == 200, response.content
            process()
            assert value.status == ("NEEDS_CLARIFICATION" if index == 0 else "READY"), value.error
    assert not outputs and len(calls) == 9
    assert value.messages.filter(kind="clarification").count() == 2
    assert "BUSINESS QUESTION CORRECTION" in calls[3]["prompt"]
    version = value.versions.get()
    assert len(version.decisions_snapshot) == 2
    prior = {artifact.name: artifact.content for artifact in version.artifacts.all()}
    response = client.post(f"/api/analyses/{value.pk}/need", {
        "need": "Explain contract cancellation and export with the archived contract exception.",
        "expected_revision": 0, "expected_version": 1, "expected_decision_revision": 2,
        "operation_id": str(uuid.uuid4()),
    }, content_type="application/json")
    assert response.status_code == 200, response.content
    assert response.json()["conclusions_stale"] and response.json()["decision_revision"] == 2
    assert len(response.json()["decisions"]) == 2 and len(response.json()["conversation"]) == 2
    version.refresh_from_db()
    assert {artifact.name: artifact.content for artifact in version.artifacts.all()} == prior
    value.refresh_from_db()
    assert value.analysis_runs.order_by("-number").first().orchestration["outputs"] == {}
