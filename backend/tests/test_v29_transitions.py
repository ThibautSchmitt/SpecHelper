"""Linked evolution retries preserve the chosen answer and use current environment SHAs."""

import uuid
from pathlib import Path

import pytest
from test_v17_api import answer as _answer
from test_v17_api import question as _question

from core.models import Job, Request, RequestMessage, ResultVersion

pytestmark = pytest.mark.django_db
answer, question = _answer, _question


def test_transition_retry_preserves_lineage_and_starts_only_one_new_dossier(client, answer, storage):
    endpoint = f"/api/questions/{answer.request_id}/requests"
    payload = {"source_version": 1, "environment_id": answer.request.environment_id,
               "need": "Add an archived contract option to the export.", "operation_id": str(uuid.uuid4())}
    first = client.post(endpoint, payload, content_type="application/json")
    repeated = client.post(endpoint, payload, content_type="application/json")
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]
    child = Request.objects.get(pk=first.json()["id"])
    assert child.attachments.count() == 1 and child.source_question_version == answer
    assert answer.request.messages.filter(kind="derived_request").count() == 1
    assert not Job.objects.exists()
    conflict = client.post(endpoint, {**payload, "need": "Add a different export."}, content_type="application/json")
    assert conflict.status_code == 409 and Request.objects.filter(source_question_version=answer).count() == 1
    answer.request.environment.repositories.update(sha="c" * 40)
    launched = client.post(f"/api/analyses/{child.pk}/analyze")
    assert launched.status_code == 200
    child.refresh_from_db()
    assert child.baseline[0]["sha"] == "c" * 40 and child.analysis_protocol == "2.4"
    assert child.analysis_runs.get().orchestration["outputs"] == {}
    assert "a" * 40 in Path(child.attachments.get().path).read_text()
    assert not answer.request.ai_sessions.filter(pk__in=child.ai_sessions.values("pk")).exists()
    parent = client.get(f"/api/analyses/{answer.request_id}").json()
    assert len(parent["derived_requests"]) == 1 and parent["latest_version"]["number"] == 1
    assert parent["messages"][-1]["data"]["child_id"] == str(child.pk)


def test_transfer_uses_selected_cycles_need_after_a_late_parent_edit(client, answer, storage):
    original = answer.request.need
    RequestMessage.objects.create(request=answer.request, role="user", kind="need", content=original)
    Request.objects.filter(pk=answer.request_id).update(need="A newer question about billing.")
    RequestMessage.objects.create(request=answer.request, role="user", kind="need_revision", content="A newer question about billing.")
    preview = client.get(f"/api/questions/{answer.request_id}/versions/1/transfer").json()
    assert original in preview["content"]
    assert "A newer question about billing." not in preview["content"]
    assert preview["summary"] == answer.explanation["summary"] and preview["result_status"] == "READY"
    frozen = ResultVersion.objects.create(
        request=answer.request, number=2, explanation=answer.explanation, baseline=answer.baseline,
        context_snapshot={"dossier": {"need": "The frozen cycle asks about exports."}},
    )
    preview = client.get(f"/api/questions/{answer.request_id}/versions/{frozen.number}/transfer").json()
    assert "The frozen cycle asks about exports." in preview["content"]
    assert "A newer question about billing." not in preview["content"]


def test_a_distinct_explicit_operation_can_create_another_legitimate_child(client, answer, storage):
    payload = {"source_version": 1, "environment_id": answer.request.environment_id,
               "need": "Add a new export option.", "include_context": False}
    ids = set()
    for _ in range(2):
        result = client.post(f"/api/questions/{answer.request_id}/requests", {
            **payload, "operation_id": str(uuid.uuid4()),
        }, content_type="application/json")
        assert result.status_code == 201
        ids.add(result.json()["id"])
    assert len(ids) == 2
