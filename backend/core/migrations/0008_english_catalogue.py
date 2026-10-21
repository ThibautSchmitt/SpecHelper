"""Use English internal instructions without changing activation flags or published results."""

from django.db import migrations


def forward(apps, schema_editor):
    from core.presets_v13 import PROFILES, SKILLS

    Profile = apps.get_model("core", "AgentProfile")
    Skill = apps.get_model("core", "SkillDefinition")
    for slug, (name, instructions) in SKILLS.items():
        Skill.objects.filter(pk=slug).update(name=name, instructions=instructions)
    for slug, data in PROFILES.items():
        Profile.objects.filter(pk=slug).update(
            name=data["name"], mission=data["mission"], instructions=data["instructions"]
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0007_instance_language")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
