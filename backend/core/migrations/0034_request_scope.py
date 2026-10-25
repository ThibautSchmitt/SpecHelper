from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0033_official_references")]

    operations = [
        migrations.AddField(model_name="request", name="scope_assessment", field=models.JSONField(default=dict)),
        migrations.AddField(model_name="request", name="scope_history", field=models.JSONField(default=list)),
        migrations.AddField(model_name="request", name="scope_clarification", field=models.TextField(blank=True)),
        migrations.AddField(model_name="request", name="scope_pending_message", field=models.TextField(blank=True)),
        migrations.AddField(model_name="request", name="scope_revision", field=models.PositiveIntegerField(default=0)),
    ]
