"""Read-only cycle progress uses accepted stages and observed waiting causes."""

import pytest

from core.conversation import progress_snapshot, waiting_causes
from core.models import AIConnection, AIIdentity

pytestmark = pytest.mark.django_db


def cycle(status="ANALYZING", outputs=None, role="analyst", **payload):
    return {"number": 1, "status": status, "steps": [], "orchestration": {"outputs": outputs or {}},
            "job__payload": {"current_role": role, **payload}}


def test_requirement_completion_is_not_a_completed_analyst_investigation():
    value = cycle(outputs={"requirement": {"questions": []}})
    value["steps"] = [{"public_role": "analyst", "roles": ["requirement"], "status": "DONE"}]
    snapshot = progress_snapshot(value, [])
    assert snapshot["stages"][0]["status"] == "waiting"
    assert not snapshot["all_stages_done"]


def test_invalidated_current_protocol_outputs_do_not_reuse_old_completion_badges():
    value = cycle(outputs={"requirement":{"questions":[]}})
    value["orchestration"]["version"] = "2.4"
    value["steps"] = [{"public_role":"analyst", "roles":["code"], "status":"DONE"}]
    assert progress_snapshot(value, [])["stages"][0]["status"] == "waiting"


def test_verifier_human_question_suspends_completion_and_partial_is_not_certification():
    outputs = {"analyst": {"questions": []}, "comparison": {"questions": []}, "verifier": {"report": {"blocking": True}, "questions": [{"id": "exception"}]}}
    value = cycle("NEEDS_CLARIFICATION", outputs, "verifier")
    messages = [{"kind": "clarification", "attribution": {"run_number": 1, "public_role": "verifier"}}]
    snapshot = progress_snapshot(value, messages)
    assert [stage["status"] for stage in snapshot["stages"]] == ["done", "done", "clarification"]
    assert not snapshot["all_stages_done"]
    value["status"] = "PARTIAL"
    outputs["verifier"]["questions"] = []
    finished = progress_snapshot(value, messages)
    assert finished["all_stages_done"] and finished["status"] == "PARTIAL"


def test_focused_check_and_interrupted_verification_remain_unfinished():
    value = cycle("ERROR", {"analyst": {"questions": []}, "comparison": {"verification": {"target": "code"}}}, "counter_analyst")
    snapshot = progress_snapshot(value, [])
    assert [stage["status"] for stage in snapshot["stages"]] == ["done", "error", "unknown"]


@pytest.mark.parametrize("status", ["QUEUED", "ANALYZING"])
def test_final_drafting_does_not_restart_a_completed_verifier(status):
    outputs = {key: {"questions": []} for key in ("analyst", "comparison", "verifier")}
    value = cycle(status, outputs, "verifier", next_checkpoint="writer")
    value["steps"] = [{"public_role": "verifier", "roles": ["writer"], "status": "RUNNING"}]
    snapshot = progress_snapshot(value, [])
    assert snapshot["checkpoint"] == "writer"
    assert snapshot["all_stages_done"]
    assert [stage["status"] for stage in snapshot["stages"]] == ["done"] * 3


@pytest.mark.parametrize("availability,expected", [("BUSY", "busy"), ("QUOTA_EXHAUSTED", "quota"), ("AUTH_ERROR", "connection_missing"), ("MODEL_UNAVAILABLE", "model_unavailable")])
def test_known_waiting_causes_are_read_without_probing_or_reserving(availability, expected):
    AIConnection.objects.all().delete()
    identity = AIIdentity.objects.create(agent="codex", status="CONNECTED", availability=availability)
    item = AIConnection.objects.create(agent="codex", identity=identity, status="CONNECTED", roles=["counter_analyst"], availability=availability)
    assert waiting_causes("counter_analyst") == [expected]
    identity.refresh_from_db()
    item.refresh_from_db()
    assert identity.availability == item.availability == availability
    snapshot = progress_snapshot(cycle("QUEUED", role="counter_analyst", waiting_reason="No available AI connection is allowed to perform this role."), [])
    assert snapshot["waiting_causes"] == [expected]
    assert snapshot["stages"][1]["status"] == "blocked"


def test_model_pools_and_available_alternatives_prevent_global_quota_claims():
    AIConnection.objects.all().delete()
    identity = AIIdentity.objects.create(agent="antigravity", status="CONNECTED", availability="AVAILABLE", quota_windows={
        "gemini-weekly": {"scope": "model_pool", "model_pool": "gemini", "exhausted": True, "remaining_percent": 0},
    })
    AIConnection.objects.create(agent="antigravity", identity=identity, model="claude-sonnet", status="CONNECTED", availability="AVAILABLE", roles=["verifier"])
    assert waiting_causes("verifier") == []
    assert waiting_causes("analyst") == ["connection_missing"]


def test_raw_scheduler_payload_and_private_prompts_are_not_public(client, environment):
    from core.models import AnalysisRun, Job, Request

    value = Request.objects.create(environment=environment, need="Explain eligibility.")
    job = Job.objects.create(kind="analysis", target=str(value.pk), status="QUEUED", payload={"current_role": "analyst", "private": "private-payload-marker"})
    AnalysisRun.objects.create(request=value, number=1, job=job, status="QUEUED")
    response = client.get(f"/api/analyses/{value.pk}")
    assert response.status_code == 200
    assert response.json()["analysis_runs"][0]["execution"]["current_role"] == "analyst"
    assert "private-payload-marker" not in response.content.decode()
    assert "job__payload" not in response.content.decode()
