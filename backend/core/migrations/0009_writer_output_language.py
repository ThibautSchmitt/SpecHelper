"""Refresh writing instructions without rewriting published artifacts or activation flags."""

from django.db import migrations


def forward(apps, schema_editor):
    from core.presets_v14 import PROFILES

    apps.get_model("core", "AgentProfile").objects.filter(pk="writer").update(
        instructions=PROFILES["writer"]["instructions"]
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0008_english_catalogue")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
