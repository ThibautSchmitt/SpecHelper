"""Activate global discovery without deleting legacy configuration or factual resources."""

import copy
import re
import unicodedata

from django.db import migrations

KNOWN_CAPABILITIES = {"read_sources", "read_attachments", "read_database", "structured_output"}
KNOWN_PROVIDERS = {"codex", "claude"}


def safe_common_text(text):
    """Conservatively leave permission-sensitive legacy prose for explicit review."""
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", text).casefold()
        if not unicodedata.combining(char)
    )
    return not re.search(
        r"\b(?:secret|secrets|token|tokens|password|credentials|write|modify|delete|update|insert|drop|alter|truncate|execute|run|script|scripts|permission|permissions|sandbox|ignore|override|bypass|disable|sudo|chmod|curl|wget|push|commit|ecrire|modifier|supprimer|executer|ignorer|contourner|desactiver|jeton|jetons)\b|\.\./|/credentials|/proc/|/etc/|/root/|~/|auth\.json|credentials\.json|https?://[^\s/]*@",
        normalized,
    )


def definition(item):
    return {
        key: copy.deepcopy(getattr(item, key))
        for key in (
            "slug",
            "name",
            "objective",
            "instructions",
            "enabled",
            "compatibility",
            "required_capabilities",
            "expected_checks",
            "version",
            "deleted",
        )
    }


def migrate_global_library(apps, schema_editor):
    Settings = apps.get_model("core", "InstanceSettings")
    Skill = apps.get_model("core", "SkillDefinition")
    Revision = apps.get_model("core", "LibraryRevision")
    review = []
    for skill in Skill.objects.filter(enabled=True, deleted=False):
        unsupported = set(skill.required_capabilities) - KNOWN_CAPABILITIES
        incompatible = set(skill.compatibility) - KNOWN_PROVIDERS
        if not unsupported and not incompatible:
            continue
        Revision.objects.get_or_create(
            kind="skill",
            slug=skill.slug,
            version=skill.version,
            defaults={"definition": definition(skill), "action": "imported", "editor": "system"},
        )
        skill.enabled = False
        skill.version += 1
        skill.save(update_fields=["enabled", "version"])
        Revision.objects.create(
            kind="skill",
            slug=skill.slug,
            version=skill.version,
            definition=definition(skill),
            action="edited",
            editor="system:migration-v2.4",
        )
        review.append(
            {
                "kind": "skill",
                "slug": skill.slug,
                "reason": "A legacy skill requests an unsupported capability or provider and remains inactive.",
            }
        )
    settings, _ = Settings.objects.get_or_create(pk=1)
    config = copy.deepcopy(settings.orchestration)
    if "v24_legacy_configuration" not in config:
        config["v24_legacy_configuration"] = copy.deepcopy(config)
        texts = [
            config.get("role_instructions", {}).get(role, "").strip()
            for role in ("analyst", "counter_analyst", "verifier")
        ]
        common = all(texts) and len(set(texts)) == 1
        promote = common and safe_common_text(texts[0])
        if "global_instructions" not in config:
            config["global_instructions"] = texts[0] if promote else ""
        if any(texts) and not promote:
            review.append(
                {
                    "kind": "instructions",
                    "reason": "Legacy role-specific or permission-sensitive instructions were preserved for review and are not applied to current system roles.",
                }
            )
        config.setdefault("global_instruction_version", 1)
        config.setdefault("tool_timeout_seconds", 300)
        config["v24_migration_review"] = review
        # Legacy association data remains for frozen runs and audit. Current discovery
        # ignores it; no environment sources, documents or connection text is removed.
        settings.orchestration = config
        settings.save(update_fields=["orchestration"])


class Migration(migrations.Migration):
    dependencies = [("core", "0029_step_execution")]
    operations = [migrations.RunPython(migrate_global_library, migrations.RunPython.noop)]
