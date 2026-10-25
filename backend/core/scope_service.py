"""Project-scope decisions precede provider reservations and costly analysis jobs."""

import hashlib
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field

from .models import Environment, Request, RequestMessage


class ScopeIn(Schema):
    model_config = ConfigDict(extra="forbid")
    need: str | None = Field(default=None, min_length=1, max_length=30000)
    message: str | None = Field(default=None, min_length=1, max_length=30000)
    environment_id: int | None = Field(default=None, ge=1)
    clarification: str | None = Field(default=None, max_length=3000)
    expected_revision: int | None = Field(default=None, ge=0)


def environment_context(environment):
    """Only saved environment facts participate; no document or URL is opened."""
    if environment is None:
        return None
    return {
        "name": environment.name,
        "context_instructions": environment.context_instructions
        if environment.instructions_enabled else "",
        "official_references": environment.official_references,
        "repository_names": list(environment.repositories.values_list("repository", flat=True)),
    }


def assess(request, *, text=None, operation="analyze", clarification=None):
    """Retain original input and a bounded, content-free decision audit."""
    from .scope_policy import classify

    text = request.need if text is None else text
    environment = request.environment if request.environment_id else None
    basis = {
        "text": text,
        "operation": operation,
        "environment_id": request.environment_id,
        "context_revision": environment.context_revision if environment else None,
        "environment": environment_context(environment),
    }
    digest = hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = request.scope_assessment if isinstance(request.scope_assessment, dict) else {}
    if clarification is None:
        clarification = request.scope_clarification if previous.get("input_sha256") == digest else ""
    request.scope_clarification = clarification.strip()
    decision = classify(
        text, environment=basis["environment"], clarification=request.scope_clarification,
        language=request.language,
        contextual_followup=operation == "continue" and request.versions.exists(),
    )
    if environment is None and decision["status"] != "OUT_OF_SCOPE":
        decision = {
            "status": "NEEDS_CLARIFICATION", "reason_code": "environment_required",
            "policy_version": "2.8",
            "message": "Select an environment so this request can be related to a project.",
            "question": "Which project environment should this request use?",
        }
    clarification_hash = hashlib.sha256(request.scope_clarification.encode()).hexdigest()
    unchanged = all((
        previous.get("input_sha256") == digest,
        previous.get("clarification_sha256") == clarification_hash,
        previous.get("status") == decision["status"],
        previous.get("reason_code") == decision["reason_code"],
        previous.get("policy_version") == decision["policy_version"],
    ))
    if not unchanged:
        request.scope_revision += 1
        request.scope_assessment = {
            **decision, "operation": operation, "revision": request.scope_revision,
            "input_sha256": digest, "clarification_sha256": clarification_hash,
            "environment_id": request.environment_id,
            "context_revision": basis["context_revision"],
            "assessed_at": timezone.now().isoformat(),
        }
        event = {key: request.scope_assessment[key] for key in (
            "operation", "revision", "status", "reason_code", "policy_version",
            "input_sha256", "environment_id", "context_revision", "assessed_at",
        )}
        history = request.scope_history if isinstance(request.scope_history, list) else []
        request.scope_history = (history + [event])[-50:]
    request.save(update_fields=[
        "scope_assessment", "scope_history", "scope_clarification", "scope_revision", "updated_at",
    ])
    return request.scope_assessment["status"] == "IN_SCOPE"


@transaction.atomic
def revise(request_id, payload, *, workflow):
    request = get_object_or_404(
        Request.objects.select_for_update(of=("self",)).select_related("environment"),
        pk=request_id, workflow=workflow,
    )
    if request.status not in {"DRAFT", "READY", "PARTIAL", "ERROR"}:
        raise HttpError(409, "Wait for the current analysis before changing its scope.")
    if payload.expected_revision is not None and payload.expected_revision != request.scope_revision:
        raise HttpError(409, "The scope assessment changed. Refresh before continuing.")
    from .business_decisions import assert_editable

    assert_editable(request)
    pending = request.scope_pending_message
    followup = bool(pending) and request.scope_assessment.get("operation") == "continue"
    if request.status != "DRAFT" and not followup:
        raise HttpError(409, "Start a new request or continue the discussion to change its scope.")
    fields = payload.model_fields_set
    if "need" in fields:
        if request.status != "DRAFT" or followup:
            raise HttpError(409, "The original request cannot be replaced during a follow-up.")
        if not payload.need or not payload.need.strip():
            raise HttpError(422, "Describe a need related to the project.")
        if not request.messages.filter(kind="need").exists():
            RequestMessage.objects.create(request=request, role="user", kind="need", content=request.need)
        request.need = payload.need.strip()
    if "message" in fields:
        if not followup or not payload.message or not payload.message.strip():
            raise HttpError(422, "Enter the follow-up you want to clarify.")
        request.scope_pending_message = payload.message.strip()
    if "environment_id" in fields:
        if request.status != "DRAFT":
            raise HttpError(409, "A follow-up keeps the original environment and frozen sources.")
        environment = get_object_or_404(Environment, pk=payload.environment_id) if payload.environment_id else None
        request.environment = environment
        request.environment_name_snapshot = environment.name if environment else ""
    request.save(update_fields=["need", "environment", "environment_name_snapshot", "scope_pending_message", "updated_at"])
    assess(
        request, text=request.scope_pending_message if followup else request.need,
        operation="continue" if followup else "analyze", clarification=payload.clarification,
    )
    return request
