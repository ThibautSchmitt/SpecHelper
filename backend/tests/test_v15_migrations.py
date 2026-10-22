import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_role_migration_keeps_existing_configuration_results_and_sessions():
    previous = [("core", "0015_legacy_source_link")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        AI = apps.get_model("core", "AIConnection")
        ai, _ = AI.objects.update_or_create(
            pk=1,
            defaults={
                "agent": "codex",
                "name": "Existing assistant",
                "model": "existing-model",
                "enabled": False,
            },
        )
        request = apps.get_model("core", "Request").objects.create(
            need="Historical request", confrontation=True, language="fr"
        )
        session = apps.get_model("core", "AISession").objects.create(
            request=request,
            connection=ai,
            runtime_id="legacy-runtime",
            model_snapshot="existing-model",
        )
        run = apps.get_model("core", "AnalysisRun").objects.create(
            request=request,
            number=1,
            steps=[{"provider": "codex", "model": "existing-model", "status": "DONE"}],
        )
        version = apps.get_model("core", "ResultVersion").objects.create(
            request=request, run=run, number=1, environment_name="Historical"
        )
        apps.get_model("core", "GeneratedArtifact").objects.create(
            version=version, name="goal.md", content="Immutable result"
        )
        names = (
            "AIConnection",
            "Request",
            "AISession",
            "AnalysisRun",
            "ResultVersion",
            "GeneratedArtifact",
        )
        snapshots = {
            name: list(apps.get_model("core", name).objects.order_by("pk").values())
            for name in names
        }
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        for name, rows in snapshots.items():
            assert (
                list(current.get_model("core", name).objects.order_by("pk").values(*rows[0]))
                == rows
            )
        migrated = current.get_model("core", "AIConnection").objects.get(pk=ai.pk)
        assert migrated.roles == ["analyst", "counter_analyst", "verifier"]
        assert migrated.skill_overrides == {} and migrated.additional_instructions == ""
        assert not migrated.enabled
        assert current.get_model("core", "AnalysisRun").objects.get(pk=run.pk).orchestration == {}
        assert current.get_model("core", "AISession").objects.get(pk=session.pk).public_role == ""
    finally:
        MigrationExecutor(connection).migrate(latest)
