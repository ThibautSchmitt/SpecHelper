"""Add an optional shared navigation skill without rewriting existing authorization."""

from django.db import migrations

from core.presets_v23 import NAVIGATION_INSTRUCTIONS


def seed_navigation(apps, schema_editor):
    Skill = apps.get_model("core", "SkillDefinition")
    Revision = apps.get_model("core", "LibraryRevision")
    item, created = Skill.objects.get_or_create(
        slug="effective-navigation",
        defaults={
            "name": "Effective source navigation",
            "objective": "Find relevant source evidence efficiently without reducing independent review.",
            "instructions": NAVIGATION_INSTRUCTIONS,
            "enabled": True,
            "required_capabilities": ["read_sources"],
        },
    )
    if created:
        Revision.objects.create(
            kind="skill",
            slug=item.slug,
            version=item.version,
            action="created",
            editor="system",
            definition={
                "slug": item.slug,
                "name": item.name,
                "objective": item.objective,
                "instructions": item.instructions,
                "enabled": item.enabled,
                "compatibility": item.compatibility,
                "required_capabilities": item.required_capabilities,
                "expected_checks": item.expected_checks,
                "version": item.version,
                "deleted": item.deleted,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0027_analysis_evidence")]
    operations = [migrations.RunPython(seed_navigation, migrations.RunPython.noop)]
