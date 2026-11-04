from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0052_single_active_ticket")]

    operations = [
        # The environment-wide timestamp cannot identify which repository changed.
        # Keep older per-repository dates unknown rather than inventing a backfill.
        migrations.AddField(
            model_name="environmentrepository",
            name="synced_at",
            field=models.DateTimeField(null=True),
        ),
    ]
