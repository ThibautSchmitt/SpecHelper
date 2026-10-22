import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_language_migration_keeps_existing_results_and_disabled_profiles():
    previous = [("core", "0006_v12_result_format")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        request = apps.get_model("core", "Request").objects.create(need="Historical request")
        version = apps.get_model("core", "ResultVersion").objects.create(
            request=request, number=1, environment_name="Historical environment"
        )
        apps.get_model("core", "GeneratedArtifact").objects.create(
            version=version, name="goal.md", content="Preserved historical artifact"
        )
        apps.get_model("core", "AgentProfile").objects.update_or_create(
            pk="reviewer",
            defaults={
                "name": "Reviewer",
                "mission": "Historical mission",
                "instructions": "Historical instructions",
                "enabled": False,
            },
        )
        apps.get_model("core", "AgentProfile").objects.update_or_create(
            pk="writer",
            defaults={
                "name": "Writer",
                "instructions": "Historical instructions",
                "enabled": False,
            },
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        from core.models import AgentProfile, GeneratedArtifact, Request, ResultVersion

        assert Request.objects.get(pk=request.pk).language == "fr"
        assert ResultVersion.objects.get(pk=version.pk).language == "fr"
        assert (
            GeneratedArtifact.objects.get(version_id=version.pk).content
            == "Preserved historical artifact"
        )
        profile = AgentProfile.objects.get(pk="reviewer")
        assert profile.enabled is False
        assert profile.mission == "Detect contradictions, weak assumptions and overlooked impacts."
        writer = AgentProfile.objects.get(pk="writer")
        assert writer.enabled is False
        assert (
            "Write all narrative content of ticket.md and goal.md in output_language"
            in writer.instructions
        )
    finally:
        MigrationExecutor(connection).migrate(latest)
