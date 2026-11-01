from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [("core", "0045_preserve_publication_associations")]

    operations = [
        migrations.AddField(
            model_name="environment",
            name="next_git_check_at",
            field=models.DateTimeField(default=timezone.now),
        ),
        migrations.AddField(
            model_name="environmentrepository",
            name="git_status",
            field=models.JSONField(default=dict),
        ),
    ]
