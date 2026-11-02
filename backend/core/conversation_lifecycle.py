"""Conversation presentation is independent of the last operation's terminal state."""

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Exists,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce, Replace

from .models import Job

STATES = ("DISCUSSION", "IN_PROGRESS", "WAITING_AI", "AWAITING_REPLY")
ACTIVE = {
    "QUEUED",
    "UNDERSTANDING",
    "ANALYZING",
    "REVIEWING",
    "GENERATING_RESULT",
    "GENERATING_TICKET",
    "CONTINUING_CONVERSATION",
}


def annotate(rows):
    # UUID storage differs between PostgreSQL and SQLite; the job target is textual.
    jobs = Job.objects.annotate(target_key=Replace("target", Value("-"), Value(""))).filter(
        kind__in=["analysis", "discussion"],
        target_key=Replace(Cast(OuterRef("pk"), CharField()), Value("-"), Value("")),
    )
    active = jobs.filter(status__in=["QUEUED", "RUNNING"])
    waiting = active.filter(payload__has_key="waiting_reason").exclude(
        payload__waiting_reason__in=["", None]
    )
    latest = jobs.annotate(activity=Coalesce("finished_at", "started_at", "created_at")).order_by(
        "-activity", "-id"
    )
    return rows.annotate(
        conversation_active=Exists(active),
        conversation_waiting=Exists(waiting),
        last_operation_status=Subquery(latest.values("status")[:1]),
        last_operation_error=Subquery(latest.values("error")[:1]),
    ).annotate(
        conversation_state=Case(
            When(conversation_waiting=True, then=Value("WAITING_AI")),
            When(conversation_active=True, then=Value("IN_PROGRESS")),
            When(
                Q(status="NEEDS_CLARIFICATION") | Q(scope_assessment__status="NEEDS_CLARIFICATION"),
                then=Value("AWAITING_REPLY"),
            ),
            default=Value("DISCUSSION"),
            output_field=CharField(),
        ),
        conversation_incident=Case(
            When(conversation_active=True, then=Value(False)),
            When(
                Q(status__in=["ERROR", "CANCELLED", *ACTIVE])
                | Q(last_operation_status__in=["ERROR", "CANCELLED"])
                | ~Q(error=""),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        ),
    )


def presentation(value):
    if not hasattr(value, "conversation_state"):
        from .models import Request

        row = (
            annotate(Request.objects.filter(pk=value.pk))
            .values(
                "conversation_state",
                "conversation_incident",
                "last_operation_status",
                "last_operation_error",
            )
            .get()
        )
    else:
        row = {
            "conversation_state": value.conversation_state,
            "conversation_incident": value.conversation_incident,
            "last_operation_status": value.last_operation_status,
            "last_operation_error": value.last_operation_error,
        }
    last_status, last_error = row.pop("last_operation_status"), row.pop("last_operation_error")
    row["incident_kind"] = (
        (
            "CANCELLED"
            if value.status == "CANCELLED" or last_status == "CANCELLED"
            else "ERROR"
            if value.status == "ERROR" or value.error or last_status == "ERROR"
            else "INTERRUPTED"
        )
        if row["conversation_incident"]
        else None
    )
    row["conversation_error"] = (
        (value.error or last_error or "") if row["conversation_incident"] else ""
    )
    return row
