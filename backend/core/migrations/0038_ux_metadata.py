from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0037_ai_priority")]
    operations = [
        migrations.AddField(model_name="request", name="display_title", field=models.CharField(blank=True, max_length=160)),
        migrations.AddField(model_name="ticketconnector", name="checked_at", field=models.DateTimeField(null=True)),
    ]
