import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_named_connections_migrate_credentials_and_sessions_without_rewriting_history():
    previous = [("core", "0010_ticket_publication")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        ai, _ = apps.get_model("core", "AIConnection").objects.update_or_create(
            pk=1,
            defaults={
                "agent": "codex",
                "account": "fixture-account",
                "status": "CONNECTED",
                "availability": "QUOTA_EXHAUSTED",
            },
        )
        apps.get_model("core", "AIConnection").objects.update_or_create(
            pk=2, defaults={"agent": "claude"}
        )
        apps.get_model("core", "GitHubConnection").objects.update_or_create(
            pk=1,
            defaults={
                "account": "fixture-source-account",
                "secret": "opaque-fixture-ciphertext",
                "status": "CONNECTED",
            },
        )
        request = apps.get_model("core", "Request").objects.create(
            need="Keep historical analysis",
            baseline=[{"repository": "org/app", "branch": "main", "sha": "a" * 40}],
        )
        session = apps.get_model("core", "AISession").objects.create(
            request=request, connection=ai, agent="codex", runtime_id="fixture-session"
        )
        version = apps.get_model("core", "ResultVersion").objects.create(
            request=request,
            number=1,
            environment_name="Historical",
            baseline=request.baseline,
        )
        apps.get_model("core", "GeneratedArtifact").objects.create(
            version=version, name="goal.md", content="Immutable historical content"
        )
        tracked = ("Request", "ResultVersion", "GeneratedArtifact", "GitHubConnection")
        snapshots = {
            name: list(apps.get_model("core", name).objects.order_by("pk").values())
            for name in tracked
        }
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        for name, rows in snapshots.items():
            assert (
                list(current.get_model("core", name).objects.order_by("pk").values(*rows[0]))
                == rows
            )
        imported = current.get_model("core", "GitConnection").objects.get(legacy_source=True)
        assert imported.secret == "opaque-fixture-ciphertext"
        assert imported.account == "fixture-source-account"
        migrated = current.get_model("core", "AIConnection").objects.get(pk=1)
        assert migrated.identity.credential_id is None
        assert migrated.identity.availability == "QUOTA_EXHAUSTED"
        assert not migrated.is_default and migrated.preference == 0
        assert migrated.name == "ChatGPT"
        historical = current.get_model("core", "AISession").objects.get(pk=session.pk)
        assert historical.runtime_id == "fixture-session"
        assert historical.identity_snapshot == migrated.identity_id
        assert historical.model_snapshot == ""
        # PostgreSQL must advance its new automatic sequence beyond imported IDs.
        third = current.get_model("core", "AIConnection").objects.create(
            agent="codex", name="Second Codex"
        )
        assert third.pk > 2
        second_git = current.get_model("core", "GitConnection").objects.create(
            name="Second account", provider="gitlab", base_url="https://gitlab.example"
        )
        assert second_git.pk > imported.pk
    finally:
        MigrationExecutor(connection).migrate(latest)
