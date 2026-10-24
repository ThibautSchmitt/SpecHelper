from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0026_business_decisions")]
    operations = [
        migrations.AddField(
            model_name="request",
            name="analysis_protocol",
            field=models.CharField(default="legacy", max_length=10),
        ),
        migrations.AddField(
            model_name="resultversion", name="evidence", field=models.JSONField(default=dict)
        ),
    ]
