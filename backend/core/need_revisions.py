"""Append-only need edits with optimistic concurrency and retry-safe submission."""

from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Schema
from ninja.errors import HttpError
from pydantic import ConfigDict, Field

from .models import Request, RequestMessage


class NeedRevisionIn(Schema):
    model_config = ConfigDict(extra="forbid")
    need: str = Field(min_length=1, max_length=30000)
    expected_revision: int = Field(ge=0)
    expected_version: int | None = Field(default=None, ge=1)
    expected_decision_revision: int = Field(ge=0)
    operation_id: UUID


def revision_state(value):
    revisions = list(value.messages.filter(kind="need_revision").order_by("created_at", "id"))
    latest = value.versions.order_by("-number").first()
    return {
        "need_revision": len(revisions),
        "conclusions_stale": bool(revisions and latest and revisions[-1].created_at > latest.created_at),
        "need_revisions": [
            {"number": index, "need": row.content, "created_at": row.created_at,
             "previous_version": row.data.get("previous_version")}
            for index, row in enumerate(revisions, 1)
        ],
    }


def append_revision(value, need, *, operation_id, previous_version=None):
    """Append a dated business event while retaining the original formulation."""
    if not value.messages.filter(kind="need").exists():
        RequestMessage.objects.create(request=value, role="user", kind="need", content=value.need)
    return RequestMessage.objects.create(
        request=value, role="user", kind="need_revision", content=need, version=previous_version,
        data={"operation_id": str(operation_id),
              "revision": value.messages.filter(kind="need_revision").count() + 1,
              "previous_need": value.need,
              "previous_version": previous_version.number if previous_version else None,
              "previous_questions": value.questions, "decision_revision": value.decision_revision},
    )


@transaction.atomic
def revise_need(analysis_id, payload, *, discussion_actor=None):
    from .business_decisions import BUSY, assert_editable, check_revision
    from .environment_context import reject_credentials
    from .services import queue_run, require_session_connection

    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id)
    need = payload.need.strip()
    if not need or "\x00" in need:
        raise HttpError(422, "Describe the updated need.")
    reject_credentials(need)
    revisions = value.messages.filter(kind="need_revision")
    previous = revisions.filter(data__operation_id=str(payload.operation_id)).first()
    if previous:
        if previous.content != need:
            raise HttpError(409, "This submission was already used for a different need.")
        return value
    if value.status in BUSY:
        raise HttpError(409, "Wait for the current analysis before editing the need.")
    assert_editable(value)
    check_revision(value, payload.expected_decision_revision, required=True)
    latest = value.versions.order_by("-number").first()
    if revisions.count() != payload.expected_revision or (latest.number if latest else None) != payload.expected_version:
        raise HttpError(409, "The analysis changed. Refresh before editing the need.")
    if need == value.need:
        raise HttpError(422, "Change the need before saving a new revision.")
    append_revision(value, need, operation_id=payload.operation_id, previous_version=latest)
    value.need = need
    value.understanding, value.questions = "", []
    value.scope_pending_message, value.scope_clarification = "", ""
    # Reassess every checkpoint. A need edit must never resume a partial checkpoint
    # whose conclusions were derived from the previous need.
    value.status, value.analysis_protocol = "DRAFT", "2.4"
    value.save()
    from .scope_service import assess

    if not assess(value):
        return value
    if value.discussion_state.get("enabled"):
        from .discussion import MessageIn, enqueue

        return enqueue(value.pk, MessageIn(expected_revision=value.discussion_state.get("revision", 0)),
                       discussion_actor or value.discussion_state.get("owner"), initial=True)
    require_session_connection(value)
    return queue_run(value)
