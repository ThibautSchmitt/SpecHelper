import json
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from ninja.errors import HttpError
from ninja.testing import TestClient

from core.models import Environment, Job, PublishedTicket, TicketConnector
from core.secrets import decrypt
from core.ticket_api import router
from core.ticket_publication import preview, publication_dict, publish

pytest_plugins = ["tests.test_ticket_publication"]
pytestmark = pytest.mark.django_db


def create_account(client, index):
    response = client.post("/ticket-connectors", json={
        "name": f"Account reference {index}", "platform": "jira",
        "base_url": "https://jira.example", "username": f"account-{index}@example.test",
        "secret": f"synthetic-publication-account-{index}",
    })
    assert response.status_code == 200, response.json()
    return response.json()


def environment_payload(environment, ids):
    return {
        "name": environment.name, "expected_revision": environment.revision,
        "database_id": environment.database_id,
        "repositories": [{"repository": r.repository, "branch": r.branch} for r in environment.repositories.all()],
        "publication_connection_ids": ids,
    }


def test_global_accounts_are_freely_named_reusable_and_do_not_duplicate_secrets(client, environment):
    api = TestClient(router)
    accounts = [create_account(api, index) for index in range(4)]
    ids = [value["id"] for value in accounts]
    assert all(value["environment_ids"] == [] for value in accounts)
    assert all("secret" not in value and "app_token" not in value for value in accounts)
    before = list(TicketConnector.objects.order_by("id").values_list("id", "secret"))
    jobs = Job.objects.count()
    result = client.patch(f"/api/environments/{environment.pk}",
        data=json.dumps(environment_payload(environment, ids)), content_type="application/json")
    assert result.status_code == 200, result.json()
    assert result.json()["publication_connection_ids"] == ids
    assert len(result.json()["publication_connections"]) == 4
    assert Job.objects.count() == jobs
    assert list(TicketConnector.objects.order_by("id").values_list("id", "secret")) == before
    other = Environment.objects.create(name="Second environment")
    other.publication_connections.add(ids[0])
    first = TicketConnector.objects.get(pk=ids[0])
    renamed = api.put(f"/ticket-connectors/{first.pk}", json={
        "name": "Any / internal designation", "platform": first.platform,
        "base_url": first.base_url, "username": first.username,
    })
    assert renamed.status_code == 200
    assert set(renamed.json()["environment_ids"]) == {environment.pk, other.pk}
    first.refresh_from_db()
    assert first.secret == before[0][1]
    assert decrypt(first.secret) == "synthetic-publication-account-0"
    environment.refresh_from_db()
    removed = client.patch(f"/api/environments/{environment.pk}",
        data=json.dumps(environment_payload(environment, [])), content_type="application/json")
    assert removed.status_code == 200
    assert removed.json()["publication_connections"] == []
    assert list(first.environments.values_list("id", flat=True)) == [other.pk]


def test_environment_creation_can_have_zero_or_multiple_publication_connections(client, environment):
    api = TestClient(router)
    ids = [create_account(api, index)["id"] for index in range(4)]
    for name, selected in [("No publication", []), ("Four accounts", ids)]:
        payload = environment_payload(environment, selected)
        payload.pop("expected_revision")
        payload["name"] = name
        response = client.post("/api/environments", data=json.dumps(payload), content_type="application/json")
        assert response.status_code == 201, response.json()
        assert response.json()["publication_connection_ids"] == selected


@pytest.mark.parametrize("index", range(4))
def test_publication_uses_the_explicit_account_and_accessible_destination(publication_context, monkeypatch, index):
    version, original, provider, payload = publication_context
    api = TestClient(router)
    ids = [create_account(api, i)["id"] for i in range(4)]
    accounts = list(TicketConnector.objects.filter(pk__in=ids).order_by("id"))
    for account in accounts:
        account.environments.add(version.request.environment_id)
        account.status = "CONNECTED"
        account.base_url = original.base_url
        account.save()
    chosen = accounts[index]
    observed = []
    def choose(value):
        observed.append((value.pk, decrypt(value.secret)))
        return provider
    monkeypatch.setattr("core.ticket_publication.provider_for", choose)
    shown = preview(version, chosen, "42")
    assert shown["title"]
    record = publish(version, chosen, {**payload, "connector_id": chosen.pk})
    assert record.connector_id == chosen.pk
    assert observed and set(observed) == {(chosen.pk, f"synthetic-publication-account-{index}")}
    assert provider.create.call_count == 1


@pytest.mark.parametrize("reason", ["unassigned", "disabled", "unverified", "unavailable"])
def test_unusable_connection_cannot_preview_or_create_a_ticket(publication_context, reason):
    version, connector, provider, payload = publication_context
    if reason == "unassigned":
        connector.environments.clear()
        assert connector.environment_id == version.request.environment_id  # Legacy column grants nothing.
    elif reason == "disabled":
        connector.enabled = False
    else:
        connector.status = "UNKNOWN" if reason == "unverified" else "UNAVAILABLE"
    connector.save()
    with pytest.raises(HttpError):
        preview(version, connector, "42")
    with pytest.raises(HttpError):
        publish(version, connector, payload)
    provider.projects.assert_not_called()
    provider.create.assert_not_called()


def test_new_write_rechecks_association_after_provider_metadata(publication_context):
    version, connector, provider, payload = publication_context
    options = provider.options.return_value
    def remove_association(*args, **kwargs):
        connector.environments.clear()
        return options
    provider.options.side_effect = remove_association
    with pytest.raises(HttpError, match="environment"):
        publish(version, connector, payload)
    assert not PublishedTicket.objects.exists()
    provider.create.assert_not_called()


def test_history_and_connection_identity_survive_rename_disable_and_unlink(publication_context):
    version, connector, provider, payload = publication_context
    record = publish(version, connector, payload)
    snapshot, digest = record.snapshot, record.payload_hash
    connector.name = "Renamed external account"
    connector.enabled = False
    connector.save()
    connector.environments.clear()
    record.refresh_from_db()
    described = publication_dict(record)
    assert described["connector_id"] == connector.pk
    assert described["connector_name"] == "Renamed external account"
    assert described["url"] == record.url
    assert record.snapshot == snapshot and record.payload_hash == digest
    assert TestClient(router).delete(f"/ticket-connectors/{connector.pk}").status_code == 409
    assert provider.create.call_count == 1


def test_unused_connection_can_be_deleted_only_after_unlinking(environment):
    api = TestClient(router)
    value = create_account(api, 1)
    connector = TicketConnector.objects.get(pk=value["id"])
    connector.environments.add(environment)
    assert api.delete(f"/ticket-connectors/{connector.pk}").status_code == 409
    connector.environments.clear()
    assert api.delete(f"/ticket-connectors/{connector.pk}").status_code == 200


@pytest.mark.django_db(transaction=True)
def test_migration_preserves_accounts_ciphertext_associations_and_ticket_history():
    previous = [("core", "0043_observed_work_progress")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        env = apps.get_model("core", "Environment").objects.create(name="Saved environment")
        Connector = apps.get_model("core", "TicketConnector")
        values = [Connector.objects.create(name=f"Existing {i}", platform="jira", base_url="https://jira.example", environment_id=env.pk if i < 2 else None, secret=f"untouched-ciphertext-{i}", app_token=f"untouched-app-token-{i}") for i in range(3)]
        request = apps.get_model("core", "Request").objects.create(environment_id=env.pk, need="Saved need")
        version = apps.get_model("core", "ResultVersion").objects.create(request_id=request.pk, number=1, environment_name=env.name)
        publication = apps.get_model("core", "PublishedTicket").objects.create(request_id=request.pk, version_id=version.pk, connector_id=values[0].pk, idempotency_key=uuid.uuid4(), external_reference="kept-reference", snapshot={"body": "original"}, payload_hash="kept-hash", status="UNCERTAIN")
        before = list(Connector.objects.order_by("id").values())
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        NewConnector = current.get_model("core", "TicketConnector")
        assert NewConnector.objects.count() == 3
        for old in before:
            item = NewConnector.objects.get(pk=old["id"])
            assert item.secret == old["secret"] and item.app_token == old["app_token"]
            assert list(item.environments.values_list("id", flat=True)) == ([env.pk] if old["environment_id"] else [])
        saved = current.get_model("core", "PublishedTicket").objects.get(pk=publication.pk)
        assert saved.connector_id == values[0].pk and saved.snapshot == {"body": "original"}
        assert saved.payload_hash == "kept-hash"
    finally:
        MigrationExecutor(connection).migrate(latest)
