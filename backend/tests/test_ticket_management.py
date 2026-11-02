"""A ticket is a retained document with distinct, independently visible deliveries."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    ConversationTicket,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
    TicketConnector,
)
from core.secrets import encrypt

pytestmark = pytest.mark.django_db


def fixture(environment):
    request = Request.objects.create(environment=environment, display_title="Contract dates", need="Explain dates", status="DISCUSSING")
    topic = RequestMessage.objects.create(request=request, role="user", kind="discussion", content="Prevent invalid dates")
    source = ResultVersion.objects.create(request=request, number=1, environment_name=environment.name)
    ticket = ConversationTicket.objects.create(request=request, source_version=source, topic_message=topic,
        draft={"title":"Check dates", "body":"## Acceptance criteria\nReject invalid periods.", "revision":1, "source_version":1, "topic_message_id":topic.pk})
    return request, source, ticket


def delivery(source, ticket, status, platform="jira", project="DATES", **extra):
    connector = TicketConnector.objects.create(name=platform+" account", platform=platform, base_url="https://tickets.example", secret=encrypt("never-disclose"))
    return PublishedTicket.objects.create(request=source.request, version=source, conversation_ticket=ticket, connector=connector,
        platform=platform, project=project, destination=uuid.uuid4().hex, idempotency_key=uuid.uuid4(), external_reference=uuid.uuid4().hex,
        title="Frozen submitted title", body="Frozen submitted content", status=status, **extra)


def test_ticket_with_multiple_deliveries_is_one_document_and_retains_each_outcome(client, environment, monkeypatch):
    request, source, ticket = fixture(environment)
    first = delivery(source,ticket,"PUBLISHED",external_id="14",external_key="DATES-14",url="https://tickets.example/14")
    second = delivery(source,ticket,"ERROR",platform="gitlab",error="Provider rejected this request")
    monkeypatch.setattr("core.ticket_publication.provider_for",lambda *args:pytest.fail("Browsing must stay local"))
    result = client.get("/api/tickets").json()
    assert result["total"] == 1
    item = result["items"][0]
    assert item["id"] == str(ticket.pk) and item["status"] == "ERROR"
    assert {p["id"] for p in item["publications"]} == {str(first.pk),str(second.pk)}
    assert item["conversation_title"] == "Contract dates"
    assert "never-disclose" not in str(result)
    detail = client.get(f"/api/tickets/{ticket.pk}").json()
    assert detail["subject"] == "Prevent invalid dates"
    assert detail["description"] == ticket.draft["body"]
    assert detail["version_number"] == 1
    assert not Job.objects.exists()
    ticket.refresh_from_db()
    assert ticket.draft["title"] == "Check dates"


@pytest.mark.parametrize("search", ["Check dates","DATES-14","14","DATES","Contract dates"])
def test_search_covers_document_destination_reference_and_conversation(client, environment, search):
    _, source, ticket = fixture(environment)
    delivery(source,ticket,"PUBLISHED",external_id="14",external_key="DATES-14")
    assert client.get("/api/tickets",{"search":search}).json()["total"] == 1


def test_filters_use_real_summary_and_uncertainty_wins_over_success(client, environment):
    _, source, ticket = fixture(environment)
    delivery(source,ticket,"PUBLISHED")
    pending = delivery(source,ticket,"PUBLISHING",platform="github")
    PublishedTicket.objects.filter(pk=pending.pk).update(updated_at=timezone.now()-timedelta(minutes=3))
    assert client.get("/api/tickets?status=UNCERTAIN").json()["total"] == 1
    assert client.get("/api/tickets?status=PUBLISHING").json()["total"] == 0
    assert client.get("/api/tickets?platform=github").json()["total"] == 1
    assert client.get("/api/tickets?platform=glpi").json()["total"] == 0
    assert client.get("/api/tickets?status=DRAFT").json()["total"] == 0
    from core.ticket_preparation import summaries
    assert summaries(source.request)[0]["status"] == "UNCERTAIN"


def test_multiple_documents_from_same_analysis_survive_archive_and_rename(client, environment):
    request, source, ticket = fixture(environment)
    other = ConversationTicket.objects.create(request=request, source_version=source, draft={"title":"Other correction", "body":"Other criteria"})
    request.archived_at, request.display_title = timezone.now(), "Renamed conversation"
    request.save()
    listing = client.get("/api/tickets").json()
    assert listing["total"] == 2
    assert {item["id"] for item in listing["items"]} == {str(ticket.pk),str(other.pk)}
    assert all(item["conversation_title"] == "Renamed conversation" for item in listing["items"])
    assert all(item["platform"] == "" and item["status"] == "DRAFT" for item in listing["items"])
    assert client.get(f"/api/tickets/{ticket.pk}").status_code == 200


def test_pagination_counts_documents_not_delivery_rows(client, environment):
    request, source, ticket = fixture(environment)
    for index in range(25):
        ConversationTicket.objects.create(request=request,source_version=source,draft={"title":f"Draft {index}"})
    delivery(source,ticket,"PUBLISHED")
    delivery(source,ticket,"ERROR")
    first=client.get("/api/tickets").json()
    second=client.get("/api/tickets?page=2").json()
    assert first["total"] == second["total"] == 26
    assert len(first["items"]) == 25 and len(second["items"]) == 1
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})


def test_confirmed_retry_does_not_leave_the_document_in_failure(client, environment):
    _, source, ticket = fixture(environment)
    failed = delivery(source,ticket,"ERROR")
    success = delivery(source,ticket,"PUBLISHED")
    PublishedTicket.objects.filter(pk=success.pk).update(destination=failed.destination)
    result=client.get("/api/tickets?status=PUBLISHED").json()
    assert result["total"] == 1
    assert result["items"][0]["status"] == "PUBLISHED"
    assert len(result["items"][0]["publications"]) == 2
    assert client.get("/api/tickets?status=ERROR").json()["total"] == 0


def test_legacy_destination_draft_is_listed_without_fabricating_a_document_or_delivery(client,environment):
    from core.models import TicketPublicationDraft

    request, source, _ = fixture(environment)
    connector=TicketConnector.objects.create(name="Legacy account",platform="gitlab",base_url="https://tickets.example")
    draft=TicketPublicationDraft.objects.create(version=source,connector=connector,project="legacy/project",content={"title":"Legacy destination edits","body":"Keep the edited body","labels":["reviewed"]})
    listed=client.get("/api/tickets?status=DRAFT&platform=gitlab&search=Legacy").json()
    assert listed["total"] == 1
    assert listed["items"][0]["kind"] == "publication_draft"
    detail=client.get(f"/api/tickets/{draft.pk}").json()
    assert detail["description"] == "Keep the edited body"
    assert detail["version_number"] == source.number
    assert detail["publications"] == []
    assert not PublishedTicket.objects.exists() and not Job.objects.exists()
