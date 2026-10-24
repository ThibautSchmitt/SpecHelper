"""Validated inherited configuration; instructions never grant technical capabilities."""

from typing import Literal

from django.db import transaction
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field, field_validator

from .catalogue import ensure_catalogue
from .models import AgentProfile, InstanceSettings, SkillDefinition
from .official_sources import WEB_POLICY

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
    max_calls: int = Field(default=10, ge=6, le=20)
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


class LegacyOrchestrationIn(OrchestrationIn):
    """Validate persisted pre-v2.3 run budgets without changing their execution contract."""

    max_calls: int = Field(default=10, ge=2, le=20)


class GlobalOrchestrationIn(Schema):
    """Current settings support partial edits and no assignment or role-text layer."""

    model_config = ConfigDict(extra="forbid")
    global_instructions: str = Field(default=WEB_POLICY, max_length=24000)
    allow_same_family_fallback: bool = True
    max_calls: int = Field(default=20, ge=6, le=100)
    tool_timeout_seconds: int = Field(default=300, ge=30, le=600)
    allow_confrontation: bool = True
    verifier_enabled: bool = True

    @field_validator("global_instructions")
    @classmethod
    def safe_global_instructions(cls, value):
        from .environment_context import reject_credentials
        from .library import validate_instruction_policy

        reject_credentials(value)
        validate_instruction_policy(value)
        return value.strip()


def validate_lists(value):
    ensure_catalogue()
    if len(set(value.active_internal_agents)) != len(value.active_internal_agents) or len(
        set(value.default_skills)
    ) != len(value.default_skills):
        raise HttpError(422, "Select each internal agent and skill only once.")
    agents = set(
        AgentProfile.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True)
    )
    skills = set(
        SkillDefinition.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True)
    )
    if not set(value.active_internal_agents) <= agents or not set(value.default_skills) <= skills:
        raise HttpError(422, "The selected internal agent or skill is unavailable.")
    if not REQUIRED_AGENTS <= set(value.active_internal_agents):
        raise HttpError(
            422, "Requirement, code and writer agents are required to produce an analysis."
        )


def get_config(protocol="2.4"):
    base = defaults()
    settings, _ = InstanceSettings.objects.get_or_create(pk=1)
    saved = settings.orchestration or {}
    if protocol == "2.4":
        current = GlobalOrchestrationIn.model_validate(
            {
                key: value
                for key, value in saved.items()
                if key in GlobalOrchestrationIn.model_fields
            }
            | {
                "allow_confrontation": True,
                "verifier_enabled": True,
                "max_calls": max(6, saved.get("max_calls", 20)),
            }
        ).model_dump()
        current.update(
            reliability_protocol="2.4",
            global_instruction_version=saved.get("global_instruction_version", 1),
            migration_review=saved.get("v24_migration_review", []),
            # Internal compatibility fields are fixed missions, never editable associations.
            active_internal_agents=sorted(REQUIRED_AGENTS | {"attachment", "reviewer"}),
            default_skills=[],
            role_instructions={role: "" for role in PUBLIC_ROLES},
            timeout_seconds=current["tool_timeout_seconds"],
        )
        return current
    # A newer administrative save must not invalidate an older persisted job's
    # budget schema. Migration retains the exact earlier configurable layer.
    saved = saved.get("v24_legacy_configuration", saved)
    merged = {**base, **{key: value for key, value in saved.items() if key in base}}
    merged["role_instructions"] = {
        **base["role_instructions"],
        **saved.get("role_instructions", {}),
    }
    # Stored settings are application-owned, but bound legacy/administrative input too.
    # Mandatory independent review is the current protocol; historical run snapshots
    # retain the older optional behavior rather than being silently reinterpreted.
    merged["allow_confrontation"] = True if protocol == "2.3" else settings.allow_confrontation
    merged["verifier_enabled"] = True if protocol == "2.3" else saved.get("verifier_enabled", True)
    if protocol == "2.3":
        merged["max_calls"] = max(6, merged["max_calls"])
    merged["max_calls"] = min(20, merged["max_calls"])
    merged["timeout_seconds"] = min(285, merged["timeout_seconds"])
    schema = OrchestrationIn if protocol == "2.3" else LegacyOrchestrationIn
    config = schema.model_validate(merged).model_dump()
    config["reliability_protocol"] = protocol
    return config


def public_config():
    config = get_config()
    if config["reliability_protocol"] == "2.4":
        return {
            key: value
            for key, value in config.items()
            if key
            not in {
                "active_internal_agents",
                "default_skills",
                "role_instructions",
                "timeout_seconds",
            }
        }
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
@transaction.atomic
def update_settings(request, payload: GlobalOrchestrationIn):
    if payload.allow_confrontation is False or not payload.verifier_enabled:
        raise HttpError(
            422, "Independent counter-analysis and verification are required for new analyses."
        )
    settings, _ = InstanceSettings.objects.select_for_update().get_or_create(pk=1)
    values = settings.orchestration.copy()
    incoming = payload.model_dump(exclude_unset=True)
    if "global_instructions" in incoming and incoming["global_instructions"] != values.get(
        "global_instructions", ""
    ):
        values["global_instruction_version"] = values.get("global_instruction_version", 1) + 1
    values.update(incoming)
    settings.orchestration = values
    settings.save(update_fields=["orchestration"])
    return public_config()


def validate_connection_overrides(roles=None, skills=None):
    if roles is not None and (len(set(roles)) != len(roles) or not set(roles) <= set(PUBLIC_ROLES)):
        raise HttpError(422, "Select each supported AI role only once.")
    if skills is not None:
        if skills:
            raise HttpError(422, "Skills are global and cannot be assigned to an AI connection.")
