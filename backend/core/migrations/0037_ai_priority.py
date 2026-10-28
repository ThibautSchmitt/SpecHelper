"""Preserve the existing selection order as a single numeric priority."""

from django.db import migrations


def migrate_priorities(apps, schema_editor):
    Connection = apps.get_model("core", "AIConnection")
    database = schema_editor.connection.alias
    rows = Connection.objects.using(database).order_by("-is_default", "preference", "pk")
    for rank, row in enumerate(rows):
        Connection.objects.using(database).filter(pk=row.pk).update(
            preference=rank * 10, is_default=False
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0036_provider_capabilities")]
    operations = [migrations.RunPython(migrate_priorities, migrations.RunPython.noop)]
