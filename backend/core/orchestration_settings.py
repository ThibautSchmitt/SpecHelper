"""Validated inherited configuration; instructions never grant technical capabilities."""

from typing import Literal

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field, field_validator

from .catalogue import ensure_catalogue
from .models import AgentProfile, InstanceSettings, SkillDefinition

PUBLIC_ROLES = ("analyst", "counter_analyst", "verifier")
REQUIRED_AGENTS = {"requirement", "code", "writer"}
Role = Literal["analyst", "counter_analyst", "verifier"]
router = Router(tags=["AI orchestration"])


def defaults():
    ensure_catalogue()
    return {
        "verifier_enabled": True,
        "allow_same_family_fallback": True,
        "max_calls": 10,
        "timeout_seconds": 285,
        "role_instructions": {role: "" for role in PUBLIC_ROLES},
        "active_internal_agents": sorted(
            REQUIRED_AGENTS
            | set(AgentProfile.objects.filter(enabled=True).values_list("slug", flat=True))
        ),
        "default_skills": list(
            SkillDefinition.objects.filter(enabled=True)
            .order_by("slug")
            .values_list("slug", flat=True)
        ),
    }


class OrchestrationIn(Schema):
    model_config = ConfigDict(extra="forbid")
    allow_confrontation: bool | None = None
    verifier_enabled: bool = True
    allow_same_family_fallback: bool = True
    max_calls: int = Field(default=10, ge=2, le=20)
    timeout_seconds: int = Field(default=285, ge=30, le=285)
    role_instructions: dict[Role, str] = Field(default_factory=dict)
    active_internal_agents: list[str]
    default_skills: list[str]

    @field_validator("role_instructions")
    @classmethod
    def bounded_instructions(cls, value):
        if any(len(text) > 12000 for text in value.values()):
            raise ValueError("Role instructions must not exceed 12000 characters.")
        return value


def validate_lists(value):
    ensure_catalogue()
    if len(set(value.active_internal_agents)) != len(value.active_internal_agents) or len(
        set(value.default_skills)
    ) != len(value.default_skills):
        raise HttpError(422, "Select each internal agent and skill only once.")
    agents = set(AgentProfile.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True))
    skills = set(SkillDefinition.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True))
    if not set(value.active_internal_agents) <= agents or not set(value.default_skills) <= skills:
        raise HttpError(422, "The selected internal agent or skill is unavailable.")
    if not REQUIRED_AGENTS <= set(value.active_internal_agents):
        raise HttpError(
            422, "Requirement, code and writer agents are required to produce an analysis."
        )


def get_config():
    base = defaults()
    settings, _ = InstanceSettings.objects.get_or_create(pk=1)
    saved = settings.orchestration or {}
    merged = {**base, **{key: value for key, value in saved.items() if key in base}}
    merged["role_instructions"] = {
        **base["role_instructions"],
        **saved.get("role_instructions", {}),
    }
    # Stored settings are application-owned, but bound legacy/administrative input too.
    merged["allow_confrontation"] = settings.allow_confrontation
    config = OrchestrationIn.model_validate(merged).model_dump()
    return config


def public_config():
    config = get_config()
    config["available_agents"] = [
        {
            "slug": item.slug,
            "name": item.name,
            "description": item.mission,
            "required": item.slug in REQUIRED_AGENTS,
        }
        for item in AgentProfile.objects.filter(deleted=False).order_by("slug")
    ]
    config["available_skills"] = [
        {"slug": item.slug, "name": item.name, "description": ""}
        for item in SkillDefinition.objects.filter(deleted=False).order_by("slug")
    ]
    return config


@router.get("/orchestration-settings")
def read_settings(request):
    return public_config()


@router.put("/orchestration-settings")
def update_settings(request, payload: OrchestrationIn):
    validate_lists(payload)
    values = payload.model_dump()
    values["role_instructions"] = {
        role: payload.role_instructions.get(role, "") for role in PUBLIC_ROLES
    }
    allow_confrontation = values.pop("allow_confrontation")
    changes = {"orchestration": values}
    if allow_confrontation is not None:
        changes["allow_confrontation"] = allow_confrontation
    InstanceSettings.objects.update_or_create(pk=1, defaults=changes)
    return public_config()


def validate_connection_overrides(roles=None, skills=None):
    if roles is not None and (len(set(roles)) != len(roles) or not set(roles) <= set(PUBLIC_ROLES)):
        raise HttpError(422, "Select each supported AI role only once.")
    if skills is not None:
        ensure_catalogue()
        known = set(SkillDefinition.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True))
        if not set(skills) <= known or any(
            type(enabled) is not bool for enabled in skills.values()
        ):
            raise HttpError(422, "Select known skills with explicit enabled or disabled overrides.")
