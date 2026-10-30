from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0040_native_analysis_policy")]
    operations = [
        migrations.AddField(
            model_name="request", name="deleted_at",
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
        migrations.AlterModelOptions(name="request", options={"base_manager_name": "all_objects"}),
        migrations.AlterModelManagers(name="request", managers=[
            ("objects", models.Manager()), ("all_objects", models.Manager()),
        ]),
    ]
