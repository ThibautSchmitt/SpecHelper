"""Presentation changes must not mutate business inputs or schedule work."""

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.analysis_titles import analysis_title
from core.models import AnalysisRun, Job, Request, RequestMessage, ResultVersion

pytestmark = pytest.mark.django_db


def test_home_categories_are_disjoint_even_with_previous_results(client, environment):
    rows = []
    for state in ["ERROR", "NEEDS_CLARIFICATION", "QUEUED", "PARTIAL", "READY"]:
        value = Request.objects.create(environment=environment, status=state, need=state)
        ResultVersion.objects.create(request=value, number=1, status="PARTIAL")
        rows.append(value)
    sections = client.get("/api/analyses/overview").json()["sections"]
    groups = [{item["id"] for item in section["items"]} for section in sections.values()]
    assert sum(map(len, groups)) == len(set.union(*groups)) == len(rows)
    assert sections["clarify"]["count"] == 2
    assert sections["active"]["count"] == 1
    assert sections["consult"]["count"] == 2
    for bucket, section in sections.items():
        filtered = client.get(f"/api/analyses?bucket={bucket}").json()
        assert {item["id"] for item in filtered["items"]} == {item["id"] for item in section["items"]}


def test_title_changes_preserve_business_need_history_and_result(client, environment):
    original = "Explain eligibility. Include the entire original context.\nDo not discard this."
    value = Request.objects.create(environment=environment, need=original, baseline={"commit": "abc"})
    RequestMessage.objects.create(request=value, role="user", kind="need", content=original)
    version = ResultVersion.objects.create(request=value, number=1, ticket={"title": "Existing deliverable"})
    assert analysis_title(value) == "Explain eligibility."
    response = client.patch(f"/api/analyses/{value.pk}/title", data=json.dumps({"title": "  Short   custom title  "}), content_type="application/json")
    assert response.status_code == 200 and response.json()["title"] == "Short custom title"
    value.refresh_from_db()
    version.refresh_from_db()
    assert value.need == original and value.baseline == {"commit": "abc"}
    assert value.messages.get().content == original
    assert version.ticket == {"title": "Existing deliverable"}
    assert client.get("/api/analyses?q=custom").json()["total"] == 1
    assert not Job.objects.exists() and not AnalysisRun.objects.exists()
    assert client.patch(f"/api/analyses/{value.pk}/title", data=json.dumps({"title": " "}), content_type="application/json").status_code == 422
    value.status = "ANALYZING"
    value.save(update_fields=["status"])
    assert client.patch(f"/api/analyses/{value.pk}/title", data=json.dumps({"title": "Unsafe concurrent edit"}), content_type="application/json").status_code == 409
    value.refresh_from_db()
    assert value.display_title == "Short custom title"


def test_long_title_is_local_and_does_not_truncate_original_need(environment):
    original = "Business context " * 50
    value = Request.objects.create(environment=environment, need=original)
    assert len(analysis_title(value)) <= 81 and analysis_title(value).endswith("…")
    value.refresh_from_db()
    assert value.need == original and value.display_title == ""


def test_prejob_scope_attention_has_no_fake_runtime_or_scheduled_job(client, environment):
    when = timezone.now() - timedelta(hours=39)
    value = Request.objects.create(environment=environment, need="Clarify eligibility", scope_assessment={"status": "NEEDS_CLARIFICATION", "assessed_at": when.isoformat(), "question": "Which contract?"})
    rows = client.get("/api/queue").json()
    assert len(rows) == 1 and rows[0]["request_id"] == str(value.pk)
    assert rows[0]["requires_attention"] is True
    assert abs((parse_datetime(rows[0]["clarification_since"]) - when).total_seconds()) < 0.001
    assert rows[0]["active_analysis_seconds"] is None and rows[0]["started_at"] is None
    assert not rows[0]["can_retry"] and not Job.objects.exists()


@pytest.mark.parametrize("scope,state", [("NEEDS_CLARIFICATION", "clarification"), ("OUT_OF_SCOPE", "scope_rejected")])
def test_followup_scope_question_takes_priority_over_an_existing_result(client, environment, scope, state):
    value = Request.objects.create(environment=environment, need="Existing question", status="READY", scope_pending_message="An ambiguous follow-up", scope_assessment={"status": scope, "operation": "continue"})
    ResultVersion.objects.create(request=value, number=1, status="READY")
    sections = client.get("/api/analyses/overview").json()["sections"]
    assert sections["clarify"]["count"] == 1 and sections["consult"]["count"] == 0
    assert sections["clarify"]["items"][0]["result_state"] == state
    assert client.get(f"/api/analyses/{value.pk}").json()["latest_version"]["number"] == 1
    activity = client.get("/api/queue").json()[0]
    assert activity["requires_attention"] is True and activity["analysis_state"] == state
    assert not Job.objects.exists()


def test_library_question_remains_actionable_without_becoming_an_analysis(client):
    job = Job.objects.create(kind="library_assistant", target="draft-1", status="DONE", payload={"outcome": "NEEDS_CLARIFICATION", "draft_kind": "skill"}, finished_at=timezone.now())
    row = client.get("/api/queue").json()[0]
    assert row["id"] == job.pk and row["queue_state"] == "PAUSED"
    assert row["requires_attention"] is True and row["request_id"] is None
    assert "library_draft=draft-1" in row["href"]


def test_deleted_targets_do_not_create_unactionable_error_badges(client):
    Job.objects.create(kind="analysis", target="deleted", status="ERROR")
    Job.objects.create(kind="sync", target="deleted", status="ERROR")
    rows = client.get("/api/queue").json()
    assert len(rows) == 2 and not any(row["requires_attention"] for row in rows)


def test_fifo_wait_is_not_reported_as_ai_shortage_and_old_errors_remain_visible(client, environment):
    queued = Request.objects.create(environment=environment, need="Queued", status="QUEUED", analysis_protocol="2.4")
    job = Job.objects.create(kind="analysis", target=str(queued.pk))
    run = AnalysisRun.objects.create(request=queued, job=job, number=1)
    failed = Request.objects.create(environment=environment, need="Old actionable failure", status="ERROR")
    failure = Job.objects.create(kind="analysis", target=str(failed.pk), status="ERROR", finished_at=timezone.now()-timedelta(days=3))
    for index in range(20):
        finished = Request.objects.create(environment=environment, need=f"Completed {index}", status="READY")
        Job.objects.create(kind="analysis", target=str(finished.pk), status="DONE", finished_at=timezone.now())
    rows = client.get("/api/queue").json()
    assert next(row for row in rows if row["id"] == job.pk)["queue_state"] == "QUEUED"
    assert next(row for row in rows if row["id"] == failure.pk)["requires_attention"] is True
    run.orchestration = {"waiting_reason": "No available verifier"}
    run.save(update_fields=["orchestration"])
    assert client.get(f"/api/analyses/{queued.pk}").json()["result_state"] == "waiting_ai"
    assert next(row for row in client.get("/api/queue").json() if row["id"] == job.pk)["queue_state"] == "WAITING_AI"
    assert client.get("/api/analyses?status=QUEUED").json()["items"][0]["result_state"] == "waiting_ai"
    newer = Job.objects.create(kind="analysis", target=str(failed.pk), status="DONE", finished_at=timezone.now())
    assert failure.pk not in {row["id"] for row in client.get("/api/queue").json()}
    assert newer.pk in {row["id"] for row in client.get("/api/queue").json()}
