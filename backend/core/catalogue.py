from .models import AgentProfile, SkillDefinition
from .presets_v16 import PROFILES, SKILLS


def ensure_catalogue():
    if AgentProfile.objects.filter(pk__in=PROFILES).count() == len(
        PROFILES
    ) and SkillDefinition.objects.filter(pk__in=SKILLS).count() == len(SKILLS):
        return
    for slug, (name, instructions) in SKILLS.items():
        SkillDefinition.objects.get_or_create(
            slug=slug, defaults={"name": name, "instructions": instructions}
        )
    for slug, data in PROFILES.items():
        profile, created = AgentProfile.objects.get_or_create(
            slug=slug, defaults={k: v for k, v in data.items() if k != "skills"}
        )
        if created:
            profile.skills.set(data["skills"])


def instructions(slug, has_database=False):
    ensure_catalogue()
    profile = AgentProfile.objects.prefetch_related("skills").get(pk=slug)
    if not profile.enabled:
        return ""
    lines = [f"ROLE: {profile.name}", profile.instructions]
    for skill in profile.skills.filter(enabled=True).order_by("slug"):
        if skill.slug == "postgres-readonly-analysis" and not has_database:
            continue
        lines += [f"SKILL {skill.slug} : {skill.instructions}"]
    return "\n".join(lines)
