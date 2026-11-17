from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0054_local_analysis_publication_retirement")]

    operations = [
        migrations.AddField(model_name="gitrepository", name="favorite", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="gitrepository", name="favorite_refs", field=models.JSONField(default=list)),
    ]
