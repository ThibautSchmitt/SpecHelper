"""Environment boundaries and recovery for historically shared ticket destinations."""

import uuid

import pytest
from ninja.errors import HttpError
from ninja.testing import TestClient

from core.models import Environment, PublishedTicket, Request, TicketConnector
from core.ticket_api import router
from core.ticket_publication import preview, publish

pytest_plugins = ["tests.test_ticket_publication"]
pytestmark = pytest.mark.django_db


def test_connector_list_and_creation_are_environment_scoped(publication_context):
    version, connector, _, _ = publication_context
    other = Environment.objects.create(name="Other environment")
    second = TicketConnector.objects.create(
        environment=other, name="Other tracker", platform="gitlab", base_url="https://other.example"
    )
    orphan = TicketConnector.objects.create(
        name="Legacy unassigned", platform="gitlab", base_url="https://legacy.example"
    )
    client = TestClient(router)
    assert {item["id"] for item in client.get("/ticket-connectors").json()} == {
        connector.pk,
        second.pk,
        orphan.pk,
    }
    selected = client.get(f"/ticket-connectors?request_id={version.request_id}").json()
    assert [item["id"] for item in selected] == [connector.pk]
    assert selected[0]["environment_id"] == version.request.environment_id
    assert [
        item["id"] for item in client.get(f"/ticket-connectors?environment_id={other.pk}").json()
    ] == [second.pk]
    missing = Request.objects.create(need="Detached historical request")
    assert client.get(f"/ticket-connectors?request_id={missing.pk}").json() == []
    data = {"name": "New tracker", "platform": "gitlab", "base_url": "https://new.example", "secret": "fixture-dedicated-destination-token"}
    assert client.post("/ticket-connectors", json=data).status_code == 422
    data["environment_id"] = other.pk
    assert client.post("/ticket-connectors", json=data).json()["environment_id"] == other.pk
    assert client.put(f"/ticket-connectors/{connector.pk}", json=data).status_code == 409
    assert (
        client.put(f"/ticket-connectors/{orphan.pk}", json=data).json()["environment_id"]
        == other.pk
    )
    assert client.get(f"/ticket-connectors?request_id={uuid.uuid4()}").status_code == 404


def test_cross_environment_preview_and_new_write_are_rejected_before_provider(publication_context):
    version, connector, provider, payload = publication_context
    connector.environment = Environment.objects.create(name="Different environment")
    connector.save()
    with pytest.raises(HttpError, match="environment"):
        preview(version, connector, payload["project"])
    with pytest.raises(HttpError, match="environment"):
        publish(version, connector, payload)
    provider.projects.assert_not_called()
    provider.create.assert_not_called()
    assert not PublishedTicket.objects.exists()


def test_historical_cross_environment_uncertain_delivery_can_only_reconcile(publication_context):
    version, connector, provider, payload = publication_context
    from core.ticket_providers import NetworkUncertain

    provider.create.side_effect = NetworkUncertain("Response lost")
    record = publish(version, connector, payload)
    assert record.status == "UNCERTAIN"
    original_snapshot = record.snapshot
    connector.environment = Environment.objects.create(name="Migrated connector owner")
    connector.save()
    provider.find.return_value = {
        "external_id": "123",
        "external_key": "#1",
        "url": "https://gitlab.example/team/project/-/issues/1",
    }
    recovered = publish(version, connector, payload)
    assert recovered.status == "PUBLISHED"
    assert recovered.connector_id == connector.pk
    assert recovered.snapshot == original_snapshot
    assert provider.create.call_count == 1
    provider.find.assert_called_once_with("42", record.external_reference)
    assert publish(version, connector, payload).pk == record.pk


def test_definitively_failed_legacy_attempt_cannot_write_outside_current_scope(publication_context):
    version, connector, provider, payload = publication_context
    from core.ticket_providers import TicketProviderError

    provider.create.side_effect = TicketProviderError("Rejected")
    record = publish(version, connector, payload)
    assert record.status == "ERROR"
    connector.environment = Environment.objects.create(name="Changed owner")
    connector.save()
    with pytest.raises(HttpError, match="environment"):
        publish(version, connector, payload)
    assert provider.create.call_count == 1


def test_migrated_clone_reconciles_with_original_connector_not_changed_clone(
    publication_context, monkeypatch
):
    version, connector, provider, payload = publication_context
    from core.ticket_providers import NetworkUncertain

    provider.create.side_effect = NetworkUncertain("Response lost")
    record = publish(version, connector, payload)
    connector.environment = Environment.objects.create(name="Historical connector owner")
    connector.save()
    clone = TicketConnector.objects.create(
        environment=version.request.environment,
        name="Independent clone",
        platform=connector.platform,
        base_url=connector.base_url,
        projects=connector.projects,
        secret="different-encrypted-secret",
    )
    seen = []

    def original_provider(value):
        seen.append(value.pk)
        return provider

    monkeypatch.setattr("core.ticket_publication.provider_for", original_provider)
    provider.find.return_value = {
        "external_id": "123",
        "external_key": "#1",
        "url": "https://gitlab.example/team/project/-/issues/1",
    }
    recovered = publish(version, clone, {**payload, "connector_id": clone.pk})
    assert recovered.pk == record.pk
    assert recovered.status == "PUBLISHED"
    assert seen == [connector.pk]
    assert provider.create.call_count == 1


def test_environment_delete_with_connector_returns_conflict_without_removing_sources(
    publication_context, client, storage
):
    import json

    version, connector, _, _ = publication_context
    environment = version.request.environment
    root = storage / "environments" / str(environment.pk)
    root.mkdir(parents=True)
    evidence = root / "existing-source"
    evidence.write_text("Preserved source data")
    response = client.delete(
        f"/api/environments/{environment.pk}",
        data=json.dumps(
            {"confirm_name": environment.name, "expected_revision": environment.revision}
        ),
        content_type="application/json",
    )
    assert response.status_code == 409
    assert "ticket connectors" in response.json()["detail"]
    assert evidence.read_text() == "Preserved source data"
    assert Environment.objects.filter(pk=environment.pk).exists()
    assert environment.repositories.count() == 1
    version.request.refresh_from_db()
    assert version.request.environment_id == environment.pk
    assert TicketConnector.objects.filter(pk=connector.pk).exists()
