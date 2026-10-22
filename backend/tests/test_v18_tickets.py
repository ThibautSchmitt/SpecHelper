"""Ticket browsing reads stored publication evidence without contacting providers."""

import uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from core.models import PublishedTicket, Request, ResultVersion, TicketConnector

pytestmark = pytest.mark.django_db


def test_ticket_detail_and_status_filter_are_local_and_truthful(environment, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Browsing must not call an external provider")

    monkeypatch.setattr("core.ticket_api.provider_for", forbidden)
    connector = TicketConnector.objects.create(
        name="Tracker", platform="github", base_url="https://github.com"
    )
    request = Request.objects.create(environment=environment, need="Export active contracts")
    version = ResultVersion.objects.create(request=request, number=1, environment_name="Staging")
    values = {}
    for index, status in enumerate(PublishedTicket.Status.values):
        values[status] = PublishedTicket.objects.create(
            request=request,
            version=version,
            connector=connector,
            platform="github",
            project="team/repo",
            destination=str(index),
            idempotency_key=uuid.uuid4(),
            external_reference=f"ref-{index}",
            title=f"Export {status}",
            body="Reviewed description",
            snapshot={"labels": ["export", "reviewed"]},
            status=status,
        )
    client = Client()
    assert client.get("/api/tickets").json()["total"] == 1
    all_items = client.get("/api/tickets?status=all").json()
    assert all_items["total"] == 4
    assert set(all_items["statuses"]) == set(PublishedTicket.Status.values)
    for status, item in values.items():
        listed = client.get(f"/api/tickets?status={status}").json()
        assert listed["total"] == 1
        detail = client.get(f"/api/tickets/{item.id}").json()
        assert detail["status"] == status
        assert detail["description"] == item.body
        assert detail["labels"] == ["export", "reviewed"]
        assert detail["payload_available"] is True
        assert detail["request_id"] == str(request.id)
        assert detail["version_number"] == 1
    pending = values["PUBLISHING"]
    PublishedTicket.objects.filter(pk=pending.pk).update(
        updated_at=timezone.now() - timedelta(minutes=2)
    )
    uncertain = client.get("/api/tickets?status=UNCERTAIN").json()
    assert uncertain["total"] == 2
    assert {item["status"] for item in uncertain["items"]} == {"UNCERTAIN"}
    assert client.get("/api/tickets?status=PUBLISHING").json()["total"] == 0
    assert client.get("/api/tickets?status=unknown").status_code == 422
    assert client.get(f"/api/tickets/{uuid.uuid4()}").status_code == 404
