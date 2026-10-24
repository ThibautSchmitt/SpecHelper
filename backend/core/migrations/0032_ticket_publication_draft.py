import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0031_mark_pending_steps")]

    operations = [
        migrations.AddField(
            model_name="publishedticket",
            name="attachment_delivery",
            field=models.JSONField(default=list),
        ),
        migrations.CreateModel(
            name="TicketPublicationDraft",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("project", models.CharField(max_length=255)),
                ("presentation", models.JSONField(default=dict)),
                ("content", models.JSONField(default=dict)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connector",
                    models.ForeignKey(
                        to="core.ticketconnector",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_drafts",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        to="core.resultversion",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_drafts",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("version", "connector", "project"),
                        name="unique_ticket_draft_destination",
                    )
                ]
            },
        ),
    ]
