import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_ticket_publication_migration_preserves_analyses_sessions_and_credentials():
    previous = [("core", "0009_writer_output_language")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        Request = apps.get_model("core", "Request")
        Version = apps.get_model("core", "ResultVersion")
        Artifact = apps.get_model("core", "GeneratedArtifact")
        Session = apps.get_model("core", "AISession")
        GitHub = apps.get_model("core", "GitHubConnection")
        request = Request.objects.create(
            need="Preserve the previous analysis", language="fr", status="READY"
        )
        version = Version.objects.create(
            request=request,
            number=1,
            ticket={"title": "Historical ticket"},
            environment_name="Archived environment",
            language="fr",
        )
        Artifact.objects.create(
            version=version, name="goal.md", content="Historical immutable goal"
        )
        session = Session.objects.create(
            request=request, agent="codex", runtime_id="historical-context"
        )
        GitHub.objects.update_or_create(
            pk=1,
            defaults={
                "account": "fixture-owner",
                "secret": "opaque-encrypted-value",
                "status": "CONNECTED",
            },
        )
        snapshots = {
            name: list(apps.get_model("core", name).objects.order_by("pk").values())
            for name in (
                "Request",
                "ResultVersion",
                "GeneratedArtifact",
                "AISession",
                "GitHubConnection",
            )
        }
        MigrationExecutor(connection).migrate(latest)
        current = MigrationExecutor(connection).loader.project_state(latest).apps
        for name, rows in snapshots.items():
            assert list(current.get_model("core", name).objects.order_by("pk").values()) == rows
        assert current.get_model("core", "PublishedTicket").objects.count() == 0
        assert current.get_model("core", "TicketConnector").objects.count() == 0
        assert (
            current.get_model("core", "AISession").objects.get(pk=session.pk).runtime_id
            == "historical-context"
        )
    finally:
        MigrationExecutor(connection).migrate(latest)
