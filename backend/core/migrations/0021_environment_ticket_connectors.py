"""Give each environment independent connectors without rewriting ticket history."""

import django.db.models.deletion
from django.db import migrations, models


def scope_legacy_connectors(apps, schema_editor):
    alias = schema_editor.connection.alias
    Connector = apps.get_model("core", "TicketConnector")
    Environment = apps.get_model("core", "Environment")
    Publication = apps.get_model("core", "PublishedTicket")
    environments = list(
        Environment.objects.using(alias).order_by("pk").values_list("pk", flat=True)
    )
    if not environments:
        # Unassigned legacy rows remain visible to administration and can be
        # explicitly assigned once the first environment has been configured.
        return
    for connector in list(Connector.objects.using(alias).order_by("pk")):
        historical = (
            Publication.objects.using(alias)
            .filter(connector_id=connector.pk, request__environment_id__isnull=False)
            .order_by("created_at", "pk")
            .values_list("request__environment_id", flat=True)
            .first()
        )
        owner = historical if historical in environments else environments[0]
        Connector.objects.using(alias).filter(pk=connector.pk).update(environment_id=owner)
        fields = {
            field.attname: getattr(connector, field.attname)
            for field in Connector._meta.fields
            if field.name not in {"id", "environment", "created_at", "updated_at"}
        }
        for environment_id in environments:
            if environment_id != owner:
                Connector.objects.using(alias).create(environment_id=environment_id, **fields)


class Migration(migrations.Migration):
    dependencies = [("core", "0020_work_item_category")]
    operations = [
        migrations.AddField(
            model_name="ticketconnector",
            name="environment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="ticket_connectors",
                to="core.environment",
            ),
        ),
        migrations.RunPython(scope_legacy_connectors, migrations.RunPython.noop),
    ]
