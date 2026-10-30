import json
import uuid
from unittest.mock import patch

import pytest

from core.agent import ProviderUnavailable
from core.models import AIConnection, AISession, Job, Request
from core.providers import connection_for, recover_orphaned_leases
from core.services import continue_conversation, enqueue_analysis
from core.worker import claim_job, perform_job
from runtime.server import classify_failure

pytestmark = pytest.mark.django_db


def assessment():
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Export active records",
        "questions": [],
        "ticket": None,
        "complexity": "simple",
    }


def available_claude():
    value = connection_for("claude")
    value.status, value.availability = "CONNECTED", "AVAILABLE"
    value.save()
    return value


def test_quota_is_skipped_and_all_unavailable_remain_queued(environment):
    claude = available_claude()
    AIConnection.objects.filter(pk=1).update(availability="QUOTA_EXHAUSTED")
    request = Request.objects.create(environment=environment, need="Export active records")
    enqueue_analysis(request.pk)
    job = claim_job()
    request.refresh_from_db()
    assert request.session.agent == "claude"
    assert job.payload["connection_ids"] == [claude.pk]
    assert AIConnection.objects.get(pk=1).availability == "QUOTA_EXHAUSTED"
    AIConnection.objects.filter(pk=claude.pk).update(availability="QUOTA_EXHAUSTED")
    other = Request.objects.create(environment=environment, need="Export another scope")
    enqueue_analysis(other.pk)
    assert claim_job() is None
    assert Job.objects.get(target=str(other.pk)).status == "QUEUED"


def test_provider_failure_falls_back_without_reusing_another_provider_session(
    environment, storage, bundle, code_report
):
    available_claude()
    request = Request.objects.create(environment=environment, need="Export active records")
    enqueue_analysis(request.pk)
    old_sid, new_sid = str(uuid.uuid4()), str(uuid.uuid4())
    answers = [
        {"session_id": old_sid, "output": assessment()},
        ProviderUnavailable("QUOTA_EXHAUSTED"),
        {"session_id": new_sid, "output": assessment()},
        {"session_id": new_sid, "output": {"analysis": code_report, "result": bundle.model_dump()}},
    ]
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=answers) as runtime,
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY"
    assert [c.args[1]["agent"] for c in runtime.call_args_list] == [
        "codex",
        "codex",
        "claude",
        "claude",
    ]
    assert runtime.call_args_list[2].args[1]["session_id"] is None
    assert AISession.objects.get(request=request, agent="codex").runtime_id == old_sid
    assert request.session.runtime_id == new_sid
    assert request.session.agent == "claude"
    assert AIConnection.objects.get(pk=1).availability == "QUOTA_EXHAUSTED"
    assert AIConnection.objects.get(pk=2).availability == "AVAILABLE"
    continue_conversation(request.pk, "Preserve existing data", 1)
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call",
            side_effect=[
                {"session_id": new_sid, "output": assessment()},
                {
                    "session_id": new_sid,
                    "output": {"analysis": code_report, "result": bundle.model_dump()},
                },
            ],
        ) as resumed,
    ):
        perform_job(claim_job())
    assert all(c.args[1]["session_id"] == new_sid for c in resumed.call_args_list)
    assert request.versions.count() == 2


def test_queue_capacity_is_reserved_and_released_between_distinct_requests(
    environment, storage, bundle, code_report, settings
):
    settings.AI_ACCOUNT_CONCURRENCY = 1
    requests = [
        Request.objects.create(environment=environment, need=f"Export active records {i}")
        for i in range(2)
    ]
    for request in requests:
        enqueue_analysis(request.pk)
    first = claim_job()
    assert claim_job() is None
    sid = str(uuid.uuid4())
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call",
            side_effect=[
                {"session_id": sid, "output": assessment()},
                {
                    "session_id": sid,
                    "output": {"analysis": code_report, "result": bundle.model_dump()},
                },
            ],
        ),
    ):
        perform_job(first)
    second = claim_job()
    assert second.target != first.target
    assert requests[0].session.context_id != requests[1].session.context_id


@pytest.mark.parametrize("two_providers", [False, True])
def test_confrontation_uses_independent_contexts_and_resumes_every_role(
    environment, storage, bundle, code_report, two_providers
):
    if two_providers:
        available_claude()
    request = Request.objects.create(
        environment=environment, need="Export active records", confrontation=True
    )
    enqueue_analysis(request.pk)
    sessions = {}
    seen = []

    def caller(path, payload, **kwargs):
        context = payload["context_id"]
        role = payload["profile"]
        seen.append(payload)
        if context in sessions:
            assert payload["session_id"] == sessions[context]
        else:
            assert payload["session_id"] is None
            sessions[context] = str(uuid.uuid4())
        if role == "requirement":
            output = assessment()
        elif role == "code":
            output = {**code_report, "evidence": ["PRIMARY-PRIVATE-CURRENT-EVIDENCE"]}
        elif role == "independent":
            assert "PRIMARY-PRIVATE-CURRENT-EVIDENCE" not in payload["prompt"]
            output = {**code_report, "evidence": ["SECONDARY-INDEPENDENT-EVIDENCE"]}
        elif role == "reviewer_writer":
            assert "PRIMARY-PRIVATE-CURRENT-EVIDENCE" in payload["prompt"]
            assert "SECONDARY-INDEPENDENT-EVIDENCE" in payload["prompt"]
            output = {
                "status": "APPROVED",
                "summary": "Independent evidence compared",
                "issues": [],
                "verification": None,
            }
        else:
            assert role == "synthesis"
            assert "PRIMARY-PRIVATE-CURRENT-EVIDENCE" in payload["prompt"]
            assert "SECONDARY-INDEPENDENT-EVIDENCE" in payload["prompt"]
            output = {
                "agreements": ["Minimal selection"],
                "divergences": [],
                "result": bundle.model_dump(),
            }
        assert payload["database"] is None
        assert "a" * 40 in payload["prompt"]
        return {"session_id": sessions[context], "output": output}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=caller),
    ):
        perform_job(claim_job())
        request.refresh_from_db()
        assert request.status == "READY", request.error
        first_goal = request.versions.get(number=1).artifacts.get(name="goal.md").content
        primary = request.session.runtime_id
        continue_conversation(request.pk, "No database migration", 1)
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY", request.error
    assert request.session.runtime_id != primary
    assert request.versions.count() == 2
    assert request.versions.get(number=1).artifacts.get(name="goal.md").content == first_goal
    assert len(sessions) == 6
    assert request.ai_sessions.exclude(public_role="").count() == 6
    assert [p["agent"] for p in seen[:5]] == [
        "codex",
        "codex",
        "claude" if two_providers else "codex",
        "claude" if two_providers else "codex",
        "codex",
    ]
    assert seen[1]["context_id"] != seen[2]["context_id"] != seen[4]["context_id"]
    assert seen[2]["context_id"] == seen[3]["context_id"]
    assert {p["context_id"] for p in seen[:5]}.isdisjoint({p["context_id"] for p in seen[5:]})
    assert [p["profile"] for p in seen[:5]] == [
        "requirement",
        "code",
        "independent",
        "reviewer_writer",
        "synthesis",
    ]


def test_runtime_classifies_only_failure_envelopes_without_leaking_output():
    failure = {"type": "turn.failed", "error": {"message": "usage_limit_reached SECRET_VALUE"}}
    assert classify_failure(json.dumps(failure).encode()) == {"kind": "QUOTA_EXHAUSTED"}
    message = {
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "usage_limit_reached"},
    }
    assert classify_failure(json.dumps(message).encode()) == {"kind": "ERROR"}
    assert classify_failure(
        json.dumps({"type": "result", "is_error": True, "result": "You've hit your limit"}).encode()
    ) == {"kind": "QUOTA_EXHAUSTED"}


def test_finished_job_does_not_leave_provider_capacity_stuck_after_restart(environment):
    AIConnection.objects.filter(pk=1).update(availability="BUSY")
    Job.objects.create(
        kind="analysis", target=str(uuid.uuid4()), status="DONE", payload={"connection_ids": [1]}
    )
    recover_orphaned_leases()
    assert AIConnection.objects.get(pk=1).availability == "AVAILABLE"
