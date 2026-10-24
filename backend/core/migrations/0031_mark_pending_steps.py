"""Preserve queued identities and payloads while marking their incremental transition."""

from django.db import migrations


def mark_pending(apps, schema_editor):
    Job = apps.get_model("core", "Job")
    for job in Job.objects.filter(kind="analysis", status="QUEUED").iterator():
        if job.payload.get("analysis_protocol") != "2.4":
            job.payload = {**job.payload, "requires_step_upgrade": True}
            job.save(update_fields=["payload"])


class Migration(migrations.Migration):
    dependencies = [("core", "0030_global_skills")]
    operations = [migrations.RunPython(mark_pending, migrations.RunPython.noop)]
