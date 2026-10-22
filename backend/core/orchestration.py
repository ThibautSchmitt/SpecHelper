"""Role eligibility, model-family diversity and explicit inherited instructions."""

import uuid

from django.db import transaction
from django.utils import timezone

from .models import AIConnection, AIIdentity, AISession, SkillDefinition
from .orchestration_settings import get_config
from .providers import candidates, identity_for, quota_group, release_connections

PUBLIC_ROLES = ("analyst", "counter_analyst", "verifier")


class RoleUnavailable(Exception):
    """A configured role must wait without discarding validated checkpoints."""

    def __init__(self, role, reason):
        self.role, self.reason = role, reason
        super().__init__(reason)


def family(connection):
    """Families follow the actual runtime provider, never accounts or display names."""
    return {"codex": "openai", "claude": "anthropic"}.get(connection.agent, connection.agent)


def select_connection(role, config, previous_family=None, used_families=(), exclude=()):
    choices = [c for c in candidates(exclude=exclude) if role in c.roles]
    if not choices:
        raise RoleUnavailable(role, "No available AI connection is allowed to perform this role.")
    different = [c for c in choices if family(c) != previous_family]
    if previous_family and different:
        choices = different
    elif previous_family and not config["allow_same_family_fallback"]:
        raise RoleUnavailable(
            role, "Waiting for an eligible connection from a different model family."
        )
    if role == "verifier":
        unused = [c for c in choices if family(c) not in used_families]
        if unused:
            choices = unused
    return choices[0], bool(previous_family and family(choices[0]) == previous_family)


def role_instructions(config, connection, public_role, internal_roles, has_database=False):
    from .catalogue import ensure_catalogue
    from .models import AgentProfile

    ensure_catalogue()
    lines = []
    for slug in internal_roles:
        if slug not in config["active_internal_agents"]:
            continue
        profile = AgentProfile.objects.filter(pk=slug).first()
        if profile:
            lines += [f"INTERNAL FUNCTION: {profile.name}", profile.instructions]
    active = set(config["default_skills"])
    if connection:
        for slug, enabled in connection.skill_overrides.items():
            if enabled:
                active.add(slug)
            else:
                active.discard(slug)
    for skill in SkillDefinition.objects.filter(pk__in=active).order_by("slug"):
        if skill.slug == "postgres-readonly-analysis" and not has_database:
            continue
        lines += [f"SKILL {skill.slug}: {skill.instructions}"]
    lines += [config["role_instructions"].get(public_role, "")]
    if connection:
        lines += [connection.additional_instructions]
    return "\n".join(lines)


@transaction.atomic
def assign_role(request, run, role, *, exclude=()):
    """Recheck live capacity at each public-role boundary and reserve only that role."""
    state = run.orchestration
    config = state.get("config") or get_config()
    list(AIIdentity.objects.select_for_update().order_by("id"))
    list(AIConnection.objects.select_for_update().order_by("id"))
    if run.job_id:
        run.job.refresh_from_db()
        release_connections(run.job.payload.get("connection_ids", []))
    previous_roles = PUBLIC_ROLES[: PUBLIC_ROLES.index(role)]
    sessions = state.setdefault("sessions", {})
    prior = [AISession.objects.get(pk=sessions[r]) for r in previous_roles if r in sessions]
    previous_family = prior[-1].family_snapshot if prior else None
    connection, fallback = select_connection(
        role, config, previous_family, [s.family_snapshot for s in prior], exclude
    )
    identity = identity_for(connection)
    session = AISession.objects.create(
        request=request,
        role=(
            "v15-"
            + {"analyst": "a", "counter_analyst": "c", "verifier": "v"}[role]
            + "-"
            + str(run.pk)
        )[:20],
        public_role=role,
        family_snapshot=family(connection),
        connection=connection,
        agent=connection.agent,
        model_snapshot=connection.model,
        identity_snapshot=identity.pk,
        connection_name_snapshot=connection.name or connection.agent,
        context_id=uuid.uuid4(),
    )
    sessions[role] = session.pk
    state["current_role"], state["waiting_role"] = role, None
    state["waiting_reason"] = ""
    state.setdefault("assignments", []).append(
        {
            "role": role,
            "public_role": role,
            "session_id": session.pk,
            "context_id": str(session.context_id),
            "connection_id": connection.pk,
            "connection_name": session.connection_name_snapshot,
            "agent": connection.agent,
            "model": connection.model or "runtime-default",
            "family": session.family_snapshot,
            "model_family": session.family_snapshot,
            "fallback": fallback,
            "at": timezone.now().isoformat(),
        }
    )
    if fallback:
        warning = {
            "code": "LIMITED_DIVERSITY",
            "role": role,
            "message": "Model-family diversity is limited; this role uses a separate independent session.",
        }
        if warning not in run.warnings:
            run.warnings.append(warning)
    run.orchestration = state
    run.save(update_fields=["orchestration", "warnings"])
    if role == "analyst":
        request.primary_session = session
        request.save(update_fields=["primary_session"])
    if run.job_id:
        run.job.payload = {
            **run.job.payload,
            "connection_ids": [connection.pk],
            "current_role": role,
            "waiting_reason": "",
            "current_assignment": state["assignments"][-1],
            "assignments": [state["assignments"][-1]],
        }
        run.job.save(update_fields=["payload"])
        ids = list(quota_group(identity).values_list("pk", flat=True))
        AIIdentity.objects.filter(pk__in=ids).update(availability="BUSY", retry_after=None)
        AIConnection.objects.filter(identity_id__in=ids).exclude(
            availability="MODEL_UNAVAILABLE"
        ).update(availability="BUSY", retry_after=None)
    return session
