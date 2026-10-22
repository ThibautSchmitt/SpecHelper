"""Migration retains original connector identities and immutable publication evidence."""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_legacy_connector_migration_copies_scope_without_rewriting_history():
    previous = [("core", "0020_work_item_category")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        Environment = apps.get_model("core", "Environment")
        first = Environment.objects.create(name="First")
        second = Environment.objects.create(name="Second")
        Connector = apps.get_model("core", "TicketConnector")
        connector = Connector.objects.create(
            name="Shared legacy tracker",
            platform="gitlab",
            base_url="https://gitlab.example",
            secret="unchanged-encrypted-secret",
            app_token="unchanged-encrypted-app-token",
            projects=["42"],
            default_project="42",
            status="CONNECTED",
        )
        for environment in (second, first):
            item = apps.get_model("core", "Request").objects.create(
                environment=environment, need="Original request", context_snapshot={"sha": "fixed"}
            )
            version = apps.get_model("core", "ResultVersion").objects.create(
                request=item,
                number=1,
                environment_name=environment.name,
                context_snapshot={"sha": "fixed"},
                ticket={"title": "Original ticket"},
            )
            apps.get_model("core", "PublishedTicket").objects.create(
                request=item,
                version=version,
                connector=connector,
                platform="gitlab",
                project="42",
                destination=str(uuid.uuid4()),
                idempotency_key=uuid.uuid4(),
                external_reference=str(uuid.uuid4()),
                snapshot={"body": "Original evidence"},
                status="UNCERTAIN",
            )
        names = ("Request", "ResultVersion", "PublishedTicket", "TicketConnector")
        before = {
            name: list(apps.get_model("core", name).objects.order_by("pk").values())
            for name in names
        }
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        for name, rows in before.items():
            query = current.get_model("core", name).objects.filter(pk__in=[r["id"] for r in rows])
            assert list(query.order_by("pk").values(*rows[0])) == rows
        connectors = current.get_model("core", "TicketConnector").objects
        assert connectors.count() == 2
        assert connectors.get(pk=connector.pk).environment_id == second.pk
        clone = connectors.get(environment_id=first.pk)
        for name in ("secret", "app_token", "projects", "default_project", "status", "base_url"):
            assert getattr(clone, name) == getattr(connector, name)
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.django_db(transaction=True)
def test_connector_without_environment_is_retained_as_unassigned():
    previous = [("core", "0020_work_item_category")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        old = executor.loader.project_state(previous).apps.get_model("core", "TicketConnector")
        item = old.objects.create(name="Orphan", platform="jira", base_url="https://jira.example")
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps.get_model("core", "TicketConnector")
        assert current.objects.get(pk=item.pk).environment_id is None
        assert current.objects.count() == 1
    finally:
        MigrationExecutor(connection).migrate(latest)
