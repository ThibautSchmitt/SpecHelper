"""Replace the bundled stack-specific preset without overwriting custom instructions."""

from django.db import migrations

from core.presets_v14 import SKILLS as PREVIOUS_SKILLS
from core.presets_v16 import SKILLS


def generic_conventions(apps, schema_editor):
    Skill = apps.get_model("core", "SkillDefinition")
    Profile = apps.get_model("core", "AgentProfile")
    Connection = apps.get_model("core", "AIConnection")
    Instance = apps.get_model("core", "InstanceSettings")
    old_slug, new_slug = "tryton-coog", "project-conventions"
    old = Skill.objects.filter(pk=old_slug).first()
    name, instructions = SKILLS[new_slug]
    if old and old.instructions != PREVIOUS_SKILLS[old_slug][1]:
        instructions = old.instructions
    replacement, _ = Skill.objects.get_or_create(
        slug=new_slug,
        defaults={
            "name": name,
            "instructions": instructions,
            "enabled": old.enabled if old else True,
        },
    )
    if old:
        for profile in Profile.objects.filter(skills=old):
            profile.skills.add(replacement)
        old.delete()
    for connection in Connection.objects.all():
        overrides = connection.skill_overrides
        if old_slug in overrides:
            overrides[new_slug] = overrides.pop(old_slug)
            connection.skill_overrides = overrides
            connection.save(update_fields=["skill_overrides"])
    for instance in Instance.objects.all():
        config = instance.orchestration
        if "default_skills" in config:
            config["default_skills"] = list(
                dict.fromkeys(
                    new_slug if slug == old_slug else slug for slug in config["default_skills"]
                )
            )
            instance.orchestration = config
            instance.save(update_fields=["orchestration"])


class Migration(migrations.Migration):
    dependencies = [("core", "0017_environment_context")]
    operations = [migrations.RunPython(generic_conventions, migrations.RunPython.noop)]
