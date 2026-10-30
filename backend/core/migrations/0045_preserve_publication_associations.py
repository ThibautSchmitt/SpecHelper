from django.db import migrations


def preserve_associations(apps, schema_editor):
    connector = apps.get_model("core", "TicketConnector")
    relation = connector.environments.through
    alias = schema_editor.connection.alias
    for value in connector.objects.using(alias).exclude(environment_id=None).iterator():
        relation.objects.using(alias).get_or_create(
            ticketconnector_id=value.pk, environment_id=value.environment_id
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0044_global_publication_connections")]

    operations = [migrations.RunPython(preserve_associations, migrations.RunPython.noop)]
