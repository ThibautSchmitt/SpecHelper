import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0043_observed_work_progress")]

    operations = [
        migrations.AddField(
            model_name="ticketconnector",
            name="environments",
            field=models.ManyToManyField(
                blank=True, related_name="publication_connections", to="core.environment"
            ),
        ),
        migrations.AddField(
            model_name="ticketconnector", name="enabled", field=models.BooleanField(default=True)
        ),
        migrations.AlterField(
            model_name="ticketconnector",
            name="environment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ticket_connectors",
                to="core.environment",
            ),
        ),
    ]
