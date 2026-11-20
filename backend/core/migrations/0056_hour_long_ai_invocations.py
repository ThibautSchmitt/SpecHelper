"""Upgrade the previously seeded invocation limit without rewriting analysis history."""

from django.db import migrations


def upgrade_timeout(apps, schema_editor):
    Settings = apps.get_model("core", "InstanceSettings")
    alias = schema_editor.connection.alias
    for settings in Settings.objects.using(alias).all().iterator():
        config = settings.orchestration or {}
        if config.get("tool_timeout_seconds") == 300:
            settings.orchestration = {**config, "tool_timeout_seconds": 3600}
            settings.save(using=alias, update_fields=["orchestration"])


class Migration(migrations.Migration):
    dependencies = [("core", "0055_git_repository_favorites")]
    operations = [migrations.RunPython(upgrade_timeout, migrations.RunPython.noop)]
