"""Unified discovery preserves legacy dossiers and reports only persisted activity."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import (
    Environment,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
    TicketConnector,
)

pytestmark = pytest.mark.django_db


def dossier(environment, workflow="request", **changes):
    return Request.objects.create(environment=environment, workflow=workflow,
                                  need="Explain the configured export.", **changes)


def test_both_internal_workflows_share_listing_and_keep_legacy_urls(client, environment):
    question = dossier(environment, "question")
    change = dossier(environment)
    result = client.get("/api/analyses").json()
    assert result["total"] == 2
    assert {item["id"] for item in result["items"]} == {str(question.pk), str(change.pk)}
    assert {item["workflow"] for item in result["items"]} == {"question", "request"}
    assert all(item["href"] == "/analyses/" + item["id"] for item in result["items"])
    for value, legacy in ((question, "questions"), (change, "requests")):
        assert client.get(f"/api/{legacy}/{value.pk}").status_code == 200
        assert client.get(f"/api/analyses/{value.pk}").json()["workflow"] == value.workflow
    assert not Job.objects.exists()


def test_unified_creation_needs_no_workflow_and_keeps_scope_gate(client, environment):
    response = client.post("/api/analyses", {"environment_id": environment.pk,
                           "need": "Explain the SQL export."}, content_type="application/json")
    assert response.status_code == 201
    result = response.json()
    assert result["intent_mode"] == "auto"
    assert result["original_need"] == "Explain the SQL export."
    assert result["scope_assessment"]["status"] == "IN_SCOPE"
    assert not Job.objects.exists()
    unrelated = client.post("/api/analyses", {"need": "Give me an apple pie recipe.",
                            "environment_id": environment.pk}, content_type="application/json").json()
    launched = client.post(f"/api/analyses/{unrelated['id']}/analyze")
    assert launched.status_code == 200
    assert launched.json()["scope_assessment"]["status"] == "OUT_OF_SCOPE"
    assert not Job.objects.exists()


def test_unresolved_intent_is_not_misrepresented_as_a_change(client, environment):
    value = dossier(environment, intent_mode="auto")
    result = client.get("/api/analyses").json()
    assert result["items"][0]["intent_resolved"] is False
    assert client.get("/api/analyses", {"workflow": "request"}).json()["total"] == 0
    Request.objects.filter(pk=value.pk).update(understanding="Explain the source behavior.", workflow="question")
    result = client.get("/api/analyses", {"workflow": "question"}).json()
    assert result["total"] == 1 and result["items"][0]["intent_resolved"] is True
    Request.objects.filter(pk=value.pk).update(understanding="", status="QUEUED")
    ResultVersion.objects.create(request=value, number=1)
    result = client.get("/api/analyses", {"workflow": "question"}).json()
    assert result["total"] == 1 and result["items"][0]["intent_resolved"] is True


def test_pagination_follows_latest_real_discussion_activity(client, environment):
    old = dossier(environment, "question")
    middle = dossier(environment)
    newest = dossier(environment)
    Request.objects.filter(pk=old.pk).update(updated_at=timezone.now()-timedelta(days=2))
    RequestMessage.objects.create(request=old, role="user", kind="discussion", content="Clarify the exception.")
    first = client.get("/api/analyses", {"page_size": 2}).json()
    second = client.get("/api/analyses", {"page_size": 2, "page": 2}).json()
    assert first["items"][0]["id"] == str(old.pk)
    assert first["has_next"] and second["has_previous"] and not second["has_next"]
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 3
    assert set(ids) == {str(value.pk) for value in (old, middle, newest)}


def test_search_and_combined_filters_deduplicate_version_matches(client, environment):
    selected = dossier(environment, "question", status="READY")
    for number in (1, 2):
        ResultVersion.objects.create(request=selected, number=number, explanation={"title": "Historical cancellation"})
    dossier(environment, "request", status="READY")
    other = Environment.objects.create(name="Other")
    dossier(other, "question", status="READY")
    response = client.get("/api/analyses", {"q": "cancellation", "workflow": "question", "status": "READY", "environment_id": environment.pk})
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1 and len(result["items"]) == 1
    assert result["items"][0]["id"] == str(selected.pk)
    assert result["items"][0]["latest_version_number"] == 2


def test_home_sections_use_real_states_and_require_an_actual_result(client, environment):
    clarify = dossier(environment, "question", status="NEEDS_CLARIFICATION")
    scope = dossier(environment, scope_assessment={"status": "NEEDS_CLARIFICATION"})
    active = dossier(environment, status="QUEUED")
    ready = dossier(environment, status="PARTIAL")
    ResultVersion.objects.create(request=ready, number=1)
    dossier(environment, status="READY")
    dossier(environment, scope_assessment={"status": "OUT_OF_SCOPE"})
    response = client.get("/api/analyses/overview")
    assert response.status_code == 200
    sections = response.json()["sections"]
    assert sections["clarify"]["count"] == 2
    assert {item["id"] for item in sections["clarify"]["items"]} == {str(clarify.pk), str(scope.pk)}
    assert sections["active"]["count"] == 1 and sections["active"]["items"][0]["id"] == str(active.pk)
    assert sections["consult"]["count"] == 1 and sections["consult"]["items"][0]["id"] == str(ready.pk)
    assert not Job.objects.exists()


def test_business_states_distinguish_drafts_publications_and_unavailable_checks(client, environment):
    row = dossier(environment, status="READY")
    version = ResultVersion.objects.create(request=row, number=1, status="READY")
    question = dossier(environment, "question", status="READY")
    ResultVersion.objects.create(request=question, number=1, status="READY")
    unavailable = dossier(environment, status="PARTIAL")
    ResultVersion.objects.create(request=unavailable, number=1, status="PARTIAL", evidence={
        "blocking": True, "database": {"status": "unavailable"},
    })
    states = {item["id"]: item["result_state"] for item in client.get("/api/analyses").json()["items"]}
    assert states[str(row.pk)] == "draft_ready" and states[str(question.pk)] == "completed"
    assert states[str(unavailable.pk)] == "verification_unavailable"
    assert client.get(f"/api/analyses/{unavailable.pk}").json()["result_state"] == "verification_unavailable"
    connector = TicketConnector.objects.create(environment=environment, platform="gitlab", base_url="https://example.test")
    PublishedTicket.objects.create(request=row, version=version, connector=connector, status="PUBLISHED",
                                   idempotency_key=uuid4(), external_reference="fixture:published")
    assert client.get(f"/api/analyses/{row.pk}").json()["result_state"] == "published"
    states = {item["id"]: item["result_state"] for item in client.get("/api/analyses").json()["items"]}
    assert states[str(row.pk)] == "published" and states[str(question.pk)] == "completed"
    RequestMessage.objects.create(request=row, role="user", kind="need_revision", content="Changed export.")
    assert client.get(f"/api/analyses/{row.pk}").json()["result_state"] == "needs_reassessment"
    states = {item["id"]: item["result_state"] for item in client.get("/api/analyses").json()["items"]}
    assert states[str(row.pk)] == "needs_reassessment"


@pytest.mark.parametrize("query", [
    {"page": 0}, {"page_size": 101}, {"status": "CERTIFIED"},
    {"workflow": "ticket"}, {"bucket": "imagined"}, {"q": "x"*501}, {"environment_id": 0},
])
def test_invalid_filters_are_rejected(client, query):
    assert client.get("/api/analyses", query).status_code == 422
