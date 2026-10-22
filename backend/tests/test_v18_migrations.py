"""Category migration preserves every historical field and immutable context."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_category_migration_preserves_historical_records_and_snapshots():
    previous = [("core", "0019_project_questions")]
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        Request = apps.get_model("core", "Request")
        snapshot = {"sha256": "historical-digest", "dossier": {"need": "Original need"}}
        for workflow in ("request", "question"):
            item = Request.objects.create(
                workflow=workflow,
                need="Historical item",
                confrontation=True,
                context_snapshot=snapshot,
            )
            run = apps.get_model("core", "AnalysisRun").objects.create(
                request=item,
                number=1,
                context_snapshot=snapshot,
            )
            version = apps.get_model("core", "ResultVersion").objects.create(
                request=item,
                run=run,
                number=1,
                context_snapshot=snapshot,
                explanation={"summary": "Existing answer"} if workflow == "question" else {},
            )
            apps.get_model("core", "GeneratedArtifact").objects.create(
                version=version,
                name="answer.md" if workflow == "question" else "goal.md",
                content="Immutable historical artifact",
            )
        names = ("Request", "AnalysisRun", "ResultVersion", "GeneratedArtifact")
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
        assert (
            current.get_model("core", "Request").objects.get(workflow="request").category == "auto"
        )
        assert (
            current.get_model("core", "Request").objects.get(workflow="question").category
            == "general"
        )
    finally:
        MigrationExecutor(connection).migrate(latest)
