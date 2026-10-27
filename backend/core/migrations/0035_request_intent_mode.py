from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0034_request_scope")]

    operations = [
        migrations.AddField(
            model_name="request", name="intent_mode",
            field=models.CharField(choices=[("explicit", "Explicit"), ("auto", "Automatic")],
                                   default="explicit", max_length=10),
        ),
    ]
