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
    request = Request.objects.create(
        environment=environment,
        display_title="Contract dates",
        need="Explain dates",
        status="DISCUSSING",
    )
    topic = RequestMessage.objects.create(
        request=request, role="user", kind="discussion", content="Prevent invalid dates"
    )
    source = ResultVersion.objects.create(
        request=request, number=1, environment_name=environment.name
    )
    ticket = ConversationTicket.objects.create(
        request=request,
        source_version=source,
        topic_message=topic,
        draft={
            "title": "Check dates",
            "body": "## Acceptance criteria\nReject invalid periods.",
            "revision": 1,
            "source_version": 1,
            "topic_message_id": topic.pk,
        },
    )
    return request, source, ticket


def delivery(source, ticket, status, platform="jira", project="DATES", **extra):
    connector = TicketConnector.objects.create(
        name=platform + " account",
        platform=platform,
        base_url="https://tickets.example",
        secret=encrypt("never-disclose"),
    )
    return PublishedTicket.objects.create(
        request=source.request,
        version=source,
        conversation_ticket=ticket,
        connector=connector,
        platform=platform,
        project=project,
        destination=uuid.uuid4().hex,
        idempotency_key=uuid.uuid4(),
        external_reference=uuid.uuid4().hex,
        title="Frozen submitted title",
        body="Frozen submitted content",
        status=status,
        **extra,
    )


@pytest.mark.parametrize("status", ["PUBLISHED", "PUBLISHING", "ERROR", "UNCERTAIN"])
def test_only_confirmed_publications_are_listed_and_other_states_remain_readable(
    client, environment, status
):
    _, source, ticket = fixture(environment)
    publication = delivery(
        source,
        ticket,
        status,
        external_id="14",
        external_key="DATES-14",
        url="https://tickets.example/browse/DATES-14",
    )
    result = client.get("/api/tickets").json()
    assert result["total"] == (1 if status == "PUBLISHED" else 0)
    assert client.get(f"/api/tickets/{publication.pk}").json()["status"] == status
    assert client.get(f"/api/tickets/{ticket.pk}").status_code == 200
    if status == "PUBLISHED":
        row = result["items"][0]
        assert row["id"] == str(publication.pk) and row["url"] == publication.url
        assert not {"body", "description", "fields", "snapshot", "attempt_history"} & row.keys()
    assert not Job.objects.exists()


@pytest.mark.parametrize("search", ["Frozen submitted", "DATES-14", "14", "jira", "DATES"])
def test_search_matches_published_title_reference_platform_and_project(client, environment, search):
    _, source, ticket = fixture(environment)
    delivery(
        source,
        ticket,
        "PUBLISHED",
        external_id="14",
        external_key="DATES-14",
        url="https://tickets.example/browse/DATES-14",
    )
    assert client.get("/api/tickets", {"search": search}).json()["total"] == 1


@pytest.mark.parametrize(
    "platform,url",
    [
        ("github", "https://tickets.example/team/repo/issues/14"),
        ("gitlab", "https://tickets.example/team/repo/-/issues/14"),
        ("jira", "https://tickets.example/browse/DATES-14"),
        ("glpi", "https://tickets.example/front/ticket.form.php?id=14"),
    ],
)
def test_official_ticket_routes_are_retained_without_provider_calls(
    client, environment, monkeypatch, platform, url
):
    _, source, ticket = fixture(environment)
    delivery(
        source,
        ticket,
        "PUBLISHED",
        platform=platform,
        external_id="14",
        external_key="DATES-14",
        url=url,
    )
    monkeypatch.setattr(
        "core.ticket_publication.provider_for",
        lambda *args: pytest.fail("History must not contact a provider"),
    )
    item = client.get("/api/tickets").json()["items"][0]
    assert item["url"] == url and item["platform"] == platform
    assert "never-disclose" not in str(item)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "javascript:alert(1)",
        "https://evil.example/browse/DATES-14",
        "https://user:password@tickets.example/browse/DATES-14",
        "https://tickets.example/redirect?url=https://evil.example",
        "https://tickets.example/browse/DATES-14#redirect",
        "https://tickets.example:444/browse/DATES-14",
        "https://tickets.example/../browse/DATES-14",
        "https://tickets.example/browse/DATES-14 ",
    ],
)
def test_historical_reference_without_a_safe_link_is_retained_without_inventing_a_url(
    client, environment, url
):
    _, source, ticket = fixture(environment)
    publication = delivery(
        source, ticket, "PUBLISHED", external_id="14", external_key="DATES-14", url=url
    )
    listed = client.get("/api/tickets").json()
    assert listed["total"] == 1 and listed["items"][0]["url"] == ""
    publication.refresh_from_db()
    assert publication.url == url and publication.status == "PUBLISHED"


@pytest.mark.parametrize("identifier,key", [("", ""), (" ", "\t")])
def test_success_without_an_external_reference_is_not_a_published_ticket(
    client, environment, identifier, key
):
    _, source, ticket = fixture(environment)
    delivery(source, ticket, "PUBLISHED", external_id=identifier, external_key=key)
    assert client.get("/api/tickets").json()["total"] == 0


def test_each_publication_is_independent_and_archiving_preserves_its_origin(client, environment):
    request, source, ticket = fixture(environment)
    first = delivery(
        source,
        ticket,
        "PUBLISHED",
        external_id="14",
        external_key="DATES-14",
        url="https://tickets.example/browse/DATES-14",
    )
    second = delivery(
        source,
        ticket,
        "PUBLISHED",
        platform="gitlab",
        external_id="42",
        url="https://tickets.example/team/repo/-/issues/42",
    )
    delivery(source, ticket, "UNCERTAIN", platform="github")
    request.archived_at = timezone.now()
    request.display_title = "Renamed conversation"
    request.save()
    listing = client.get("/api/tickets").json()
    assert listing["total"] == 2
    assert {item["id"] for item in listing["items"]} == {str(first.pk), str(second.pk)}
    assert all(
        item["request_id"] == str(request.pk) and not item["analysis_deleted"]
        for item in listing["items"]
    )
    assert client.get("/api/tickets?platform=gitlab").json()["total"] == 1
    assert client.get("/api/tickets?environment=Missing").json()["total"] == 0
    assert client.get("/api/tickets?status=UNCERTAIN").json()["total"] == 0
    from core.ticket_preparation import summaries

    assert summaries(request)[0]["status"] == "UNCERTAIN"


def test_drafts_stay_in_their_conversation_and_do_not_appear_in_history(client, environment):
    from core.models import TicketPublicationDraft

    request, source, ticket = fixture(environment)
    connector = TicketConnector.objects.create(
        name="Legacy account", platform="gitlab", base_url="https://tickets.example"
    )
    draft = TicketPublicationDraft.objects.create(
        version=source,
        connector=connector,
        project="legacy/project",
        content={"title": "Legacy edits", "body": "Keep this body"},
    )
    assert client.get("/api/tickets").json()["total"] == 0
    assert client.get(f"/api/tickets/{ticket.pk}").json()["description"] == ticket.draft["body"]
    assert client.get(f"/api/tickets/{draft.pk}").json()["description"] == "Keep this body"
    assert (
        client.get(
            f"/api/analyses/{request.pk}/ticket-preparation", {"ticket_id": str(ticket.pk)}
        ).status_code
        == 200
    )
    assert not Job.objects.exists()


def test_pagination_counts_external_publications_and_preserves_recorded_dates(client, environment):
    _, source, ticket = fixture(environment)
    at = timezone.now() - timedelta(days=2)
    for index in range(26):
        delivery(source, ticket, "PUBLISHED", external_id=str(index + 1), finished_at=at)
    first = client.get("/api/tickets").json()
    second = client.get("/api/tickets?page=2").json()
    assert first["total"] == second["total"] == 26
    assert len(first["items"]) == 25 and len(second["items"]) == 1
    assert first["items"][0]["published_at"].startswith(at.strftime("%Y-%m-%d"))
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})


def test_history_is_sorted_by_recorded_publication_date_with_a_legacy_fallback(client, environment):
    _, source, ticket = fixture(environment)
    now = timezone.now()
    recent = delivery(source, ticket, "PUBLISHED", external_id="1", finished_at=now)
    old = delivery(
        source, ticket, "PUBLISHED", external_id="2", finished_at=now - timedelta(days=2)
    )
    legacy = delivery(source, ticket, "PUBLISHED", external_id="3")
    PublishedTicket.objects.filter(pk=recent.pk).update(created_at=now - timedelta(days=10))
    PublishedTicket.objects.filter(pk=legacy.pk).update(created_at=now - timedelta(days=1))
    assert [item["id"] for item in client.get("/api/tickets").json()["items"]] == [
        str(recent.pk),
        str(legacy.pk),
        str(old.pk),
    ]
