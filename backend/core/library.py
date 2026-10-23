"""Portable, versioned instructions; permissions belong exclusively to the runtime."""

import copy

from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field, field_validator

from .catalogue import ensure_catalogue
from .environment_context import reject_credentials
from .models import AgentProfile, AIConnection, Environment, LibraryRevision, SkillDefinition

router = Router(tags=["Agent and skill library"])
MODELS = {"agent": AgentProfile, "skill": SkillDefinition}
CAPABILITIES = {"read_sources", "read_attachments", "read_database", "structured_output"}
PROVIDERS = {"codex", "claude"}


def editor_for(request):
    """Identify an editing session pseudonymously, without recording credentials."""
    from .web_security import actor_key

    return "session:" + actor_key(request)[:20]


class DefinitionIn(Schema):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=4000)
    instructions: str = Field(min_length=1, max_length=12000)
    enabled: bool = True
    compatibility: list[str] = Field(default_factory=list, max_length=2)
    required_capabilities: list[str] = Field(default_factory=list, max_length=4)
    skills: list[str] = Field(default_factory=list, max_length=100)
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("name", "objective", "instructions")
    @classmethod
    def safe_text(cls, text):
        if not text.strip() or "\x00" in text:
            raise ValueError("Enter nonempty text without null characters.")
        return text.strip()


class SelectionIn(Schema):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    agents: list[str] | None = Field(default=None, max_length=100)
    skills: list[str] | None = Field(default=None, max_length=100)


def model_for(kind):
    if kind not in MODELS:
        raise HttpError(404, "Unknown library type.")
    return MODELS[kind]


def definition(item, kind):
    result = {
        "slug": item.slug,
        "name": item.name,
        "objective": item.mission if kind == "agent" else item.objective,
        "instructions": item.instructions,
        "enabled": item.enabled,
        "compatibility": item.compatibility,
        "required_capabilities": item.required_capabilities,
        "version": item.version,
        "deleted": item.deleted,
    }
    if kind == "agent":
        result["skills"] = list(item.skills.order_by("slug").values_list("slug", flat=True))
    return result


def record(item, kind, action, editor="administrator"):
    return LibraryRevision.objects.create(
        kind=kind,
        slug=item.slug,
        version=item.version,
        definition=definition(item, kind),
        action=action,
        editor=editor,
    )


def preserve(item, kind):
    """Seed an existing built-in revision without rewriting its established contents."""
    LibraryRevision.objects.get_or_create(
        kind=kind,
        slug=item.slug,
        version=item.version,
        defaults={"definition": definition(item, kind), "action": "imported", "editor": "system"},
    )


def validate_definition(payload, kind):
    if (
        len(set(payload.compatibility)) != len(payload.compatibility)
        or not set(payload.compatibility) <= PROVIDERS
    ):
        raise HttpError(422, "Select supported provider adapters only once.")
    if (
        len(set(payload.required_capabilities)) != len(payload.required_capabilities)
        or not set(payload.required_capabilities) <= CAPABILITIES
    ):
        raise HttpError(
            422, "Declarative instructions cannot request additional runtime permissions."
        )
    if kind == "skill" and payload.skills:
        raise HttpError(422, "Only agents can require skills.")
    known = set(
        SkillDefinition.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True)
    )
    if len(set(payload.skills)) != len(payload.skills) or not set(payload.skills) <= known:
        raise HttpError(422, "Select active library skills only once.")
    for text in (payload.slug, payload.name, payload.objective, payload.instructions):
        reject_credentials(text)


@transaction.atomic
def save_definition(kind, payload, slug=None, editor="administrator"):
    ensure_catalogue()
    model = model_for(kind)
    validate_definition(payload, kind)
    if slug is None:
        if (
            model.objects.filter(pk=payload.slug).exists()
            or LibraryRevision.objects.filter(kind=kind, slug=payload.slug).exists()
        ):
            raise HttpError(
                409, "This library identifier already exists. Choose another identifier."
            )
        item = model(slug=payload.slug)
        action = "created"
    else:
        item = get_object_or_404(model.objects.select_for_update(), pk=slug, deleted=False)
        if payload.slug != slug:
            raise HttpError(422, "The library identifier cannot change.")
        if payload.expected_version != item.version:
            raise HttpError(409, "The definition has changed. Refresh before editing.")
        preserve(item, kind)
        item.version += 1
        action = "edited"
    item.name, item.instructions, item.enabled = payload.name, payload.instructions, payload.enabled
    item.compatibility, item.required_capabilities = (
        payload.compatibility,
        payload.required_capabilities,
    )
    setattr(item, "mission" if kind == "agent" else "objective", payload.objective)
    item.save()
    if kind == "agent":
        item.skills.set(payload.skills)
    record(item, kind, action, editor)
    return definition(item, kind)


@router.get("/library/{kind}")
def list_definitions(request, kind: str):
    ensure_catalogue()
    model = model_for(kind)
    return [definition(item, kind) for item in model.objects.filter(deleted=False).order_by("slug")]


@router.post("/library/{kind}")
def create_definition(request, kind: str, payload: DefinitionIn):
    return save_definition(kind, payload, editor=editor_for(request))


@router.put("/library/{kind}/{slug}")
def edit_definition(request, kind: str, slug: str, payload: DefinitionIn):
    return save_definition(kind, payload, slug, editor_for(request))


@router.get("/library/{kind}/{slug}/versions")
@transaction.atomic
def versions(request, kind: str, slug: str):
    model = model_for(kind)
    item = model.objects.select_for_update().filter(pk=slug).first()
    if item:
        preserve(item, kind)
    rows = LibraryRevision.objects.filter(kind=kind, slug=slug).order_by("-version")
    if not rows.exists():
        raise HttpError(404, "Library definition not found.")
    return list(rows.values("version", "definition", "action", "editor", "created_at"))


@router.delete("/library/{kind}/{slug}")
@transaction.atomic
def delete_definition(request, kind: str, slug: str, expected_version: int):
    item = get_object_or_404(model_for(kind).objects.select_for_update(), pk=slug, deleted=False)
    if item.version != expected_version:
        raise HttpError(409, "The definition has changed. Refresh before editing.")
    if item.enabled:
        raise HttpError(
            409, "Disable the definition before deleting it. Historical versions are retained."
        )
    from .orchestration_settings import REQUIRED_AGENTS

    if kind == "agent" and slug in REQUIRED_AGENTS:
        raise HttpError(409, "This built-in agent is required by the analysis workflow.")
    if kind == "skill" and item.agents.filter(deleted=False).exists():
        raise HttpError(409, "Remove this skill from its agents before deleting it.")
    key = "agents" if kind == "agent" else "skills"
    if any(slug in (env.library_selection.get(key) or []) for env in Environment.objects.all()):
        raise HttpError(
            409, "Remove this definition from environment selections before deleting it."
        )
    preserve(item, kind)
    item.version += 1
    item.deleted = True
    item.save(update_fields=["version", "deleted"])
    record(item, kind, "deleted", editor_for(request))
    return {"deleted": True, "historical_versions_retained": True}


def selection(environment):
    return {
        "revision": environment.library_revision,
        "agents": environment.library_selection.get("agents"),
        "skills": environment.library_selection.get("skills"),
    }


@router.get("/environments/{environment_id}/library")
def read_selection(request, environment_id: int):
    return selection(get_object_or_404(Environment, pk=environment_id))


@router.put("/environments/{environment_id}/library")
@transaction.atomic
def update_selection(request, environment_id: int, payload: SelectionIn):
    ensure_catalogue()
    env = get_object_or_404(Environment.objects.select_for_update(), pk=environment_id)
    if env.library_revision != payload.expected_revision:
        raise HttpError(
            409, "The environment library selection has changed. Refresh before editing."
        )
    for key, model in (("agents", AgentProfile), ("skills", SkillDefinition)):
        values = getattr(payload, key)
        if values is not None and (
            len(values) != len(set(values))
            or not set(values)
            <= set(model.objects.filter(enabled=True, deleted=False).values_list("slug", flat=True))
        ):
            raise HttpError(422, "Select active library definitions only once.")
    from .orchestration_settings import REQUIRED_AGENTS

    if payload.agents is not None and not REQUIRED_AGENTS <= set(payload.agents):
        raise HttpError(
            422, "Requirement, code and writer agents are required to produce an analysis."
        )
    env.library_selection = {"agents": payload.agents, "skills": payload.skills}
    env.library_revision += 1
    env.save(update_fields=["library_selection", "library_revision"])
    return selection(env)


@transaction.atomic
def snapshot(environment=None):
    """Freeze complete definitions, not live references that drift during a run."""
    ensure_catalogue()
    chosen = environment.library_selection if environment else {}
    result = {
        "agents": [],
        "skills": [],
        "environment_revision": environment.library_revision if environment else None,
    }
    for key, kind in (("agents", "agent"), ("skills", "skill")):
        rows = (
            model_for(kind)
            .objects.select_for_update()
            .filter(enabled=True, deleted=False)
            .order_by("slug")
        )
        if chosen.get(key) is not None:
            rows = rows.filter(pk__in=chosen[key])
        for item in rows:
            preserve(item, kind)
            result[key].append(definition(item, kind))
    return result


@router.post("/environments/{environment_id}/library/preview")
def preview_draft(request, environment_id: int, connection_id: int, payload: SelectionIn):
    from .orchestration_settings import get_config

    env = get_object_or_404(Environment, pk=environment_id)
    if env.library_revision != payload.expected_revision:
        raise HttpError(
            409, "The environment library selection has changed. Refresh before editing."
        )
    connection = get_object_or_404(AIConnection, pk=connection_id)
    env.library_selection = {"agents": payload.agents, "skills": payload.skills}
    config = get_config()
    return preview_configuration(env, connection, config)


def effective(library, connection, internal_roles, config, has_database=False):
    """Adapt declarative text only; unsupported capabilities never widen a sandbox."""
    problems, lines = [], []
    provider = connection.agent if connection else "codex"
    selected = {item["slug"]: item for item in library["agents"]}
    skills = {item["slug"]: item for item in library["skills"]}
    active = set(config["default_skills"]) & skills.keys()
    if connection:
        for slug, enabled in connection.skill_overrides.items():
            if enabled and slug in skills:
                active.add(slug)
            elif enabled:
                problems.append(
                    {"slug": slug, "kind": "skill", "reason": "Skill unavailable in environment"}
                )
            elif not enabled:
                active.discard(slug)
    capabilities = CAPABILITIES - ({"read_database"} if not has_database else set())

    def append(item, label):
        incompatible = item["compatibility"] and provider not in item["compatibility"]
        missing = set(item["required_capabilities"]) - capabilities
        if incompatible or missing:
            problems.append(
                {
                    "slug": item["slug"],
                    "kind": label.lower(),
                    "reason": "Provider incompatibility"
                    if incompatible
                    else "Required capability unavailable",
                    "missing_capabilities": sorted(missing),
                }
            )
        lines.extend(
            [f"{label} {item['slug']}: {item['name']} (v{item['version']})", item["instructions"]]
        )

    from .presets_v16 import PROFILES

    required = [*internal_roles, *(slug for slug in selected if slug not in PROFILES)]
    for slug in dict.fromkeys(required):
        if slug not in config["active_internal_agents"] and slug in PROFILES:
            continue
        agent = selected.get(slug)
        if not agent:
            problems.append(
                {"slug": slug, "kind": "agent", "reason": "Agent unavailable in environment"}
            )
            continue
        append(agent, "AGENT")
        for skill in agent.get("skills", []):
            if skill == "postgres-readonly-analysis" and not has_database:
                continue
            if skill not in skills:
                problems.append(
                    {
                        "slug": skill,
                        "kind": "skill",
                        "reason": "Required skill unavailable in environment",
                    }
                )
            elif connection and connection.skill_overrides.get(skill) is False:
                problems.append(
                    {
                        "slug": skill,
                        "kind": "skill",
                        "reason": "Required skill disabled for connection",
                    }
                )
            else:
                active.add(skill)
    for slug in sorted(active):
        if slug == "postgres-readonly-analysis" and not has_database:
            continue
        append(skills[slug], "SKILL")
    return {
        "compatible": not problems,
        "incompatibilities": problems,
        "instructions": "\n".join(lines),
        "library": copy.deepcopy(library),
        "provider": provider,
    }


@router.get("/environments/{environment_id}/library/preview")
def preview(request, environment_id: int, connection_id: int):
    from .orchestration_settings import get_config

    env = get_object_or_404(Environment, pk=environment_id)
    connection = get_object_or_404(AIConnection, pk=connection_id)
    return preview_configuration(env, connection, get_config())


def preview_configuration(environment, connection, config):
    value = effective(
        snapshot(environment),
        connection,
        config["active_internal_agents"],
        config,
        bool(environment.database_id),
    )
    value.update(
        connection_name=connection.name,
        model=connection.model or "runtime-default",
        roles=connection.roles,
        role_instructions=config["role_instructions"],
        connection_instructions=connection.additional_instructions,
        adapter="codex_cli" if connection.agent == "codex" else "claude_code_cli",
    )
    value["instructions"] += (
        "\n"
        + "\n".join(
            f"PUBLIC ROLE {role}: {text}"
            for role, text in config["role_instructions"].items()
            if text
        )
        + "\n"
        + connection.additional_instructions
    )
    return value
