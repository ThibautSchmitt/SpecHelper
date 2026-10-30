"""Unified read views over existing Questions and Requests, preserving their history."""

from math import ceil
from typing import Literal
from uuid import UUID

from django.db import transaction
from django.db.models import DateTimeField, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import File, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.responses import Status
from pydantic import ConfigDict, Field

from .models import (
    AnalysisRun,
    Environment,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
    StepExecution,
)
from .need_revisions import NeedRevisionIn

router = Router(tags=["Analyses"])
ACTIVE_STATUSES = [
    status for status in Request.Status.values
    if status not in {"DRAFT", "DISCUSSING", "NEEDS_CLARIFICATION", "READY", "PARTIAL", "ERROR", "CANCELLED"}
]


class AnalysisIn(Schema):
    model_config = ConfigDict(extra="forbid")
    environment_id: int | None = None
    need: str = Field(min_length=1, max_length=30000)
    category: str = Field(default="auto", max_length=20)
    confrontation: bool = False


@router.post("/analyses", response={201: dict})
@transaction.atomic
def create_analysis(request, payload: AnalysisIn):
    from .api import request_dict
    from .creation_policy import automatic_comparison, creation_settings
    from .discussion_access import actor
    from .scope_service import assess

    need = payload.need.strip()
    if not need:
        raise HttpError(422, "Describe a need related to the project.")
    options = creation_settings()
    environment = get_object_or_404(Environment, pk=payload.environment_id) if payload.environment_id else None
    value = Request.objects.create(
        environment=environment, environment_name_snapshot=environment.name if environment else "",
        need=need, workflow="question", intent_mode="auto", analysis_protocol="2.4", category=payload.category,
        discussion_state={"enabled": True, "owner": actor(request), "private": True, "revision": 0, "mode": "discussion"},
        confrontation=automatic_comparison(options), language=options.language,
    )
    RequestMessage.objects.create(request=value, role="user", kind="need", content=need)
    assess(value)
    return Status(201, request_dict(value, full=True))


def analysis_rows():
    """Order by actual discussion/result activity without one query per dossier."""
    versions = ResultVersion.objects.filter(request_id=OuterRef("pk")).order_by("-number")
    messages = RequestMessage.objects.filter(request_id=OuterRef("pk")).order_by("-created_at", "-id")
    publications = PublishedTicket.objects.filter(request_id=OuterRef("pk")).order_by("-updated_at", "id")
    runs = AnalysisRun.objects.filter(request_id=OuterRef("pk")).order_by("-number")
    return Request.objects.select_related("environment", "source_question_version").annotate(
        result_number=Subquery(versions.values("number")[:1]),
        latest_wait_reason=Subquery(runs.values("job__payload__waiting_reason")[:1]),
        latest_run_wait_reason=Subquery(runs.values("orchestration__waiting_reason")[:1]),
        result_status=Subquery(versions.values("status")[:1]),
        result_created_at=Subquery(versions.values("created_at")[:1]),
        need_revised_at=Subquery(messages.filter(kind="need_revision").values("created_at")[:1]),
        result_database_status=Subquery(versions.values("evidence__database__status")[:1]),
        result_blocking=Subquery(versions.values("evidence__blocking")[:1]),
        result_limits=Subquery(versions.values("evidence__limitations")[:1]),
        published_latest=Exists(PublishedTicket.objects.filter(
            request_id=OuterRef("pk"), version__number=OuterRef("result_number"), status="PUBLISHED",
        )),
        has_result=Exists(versions),
        latest_activity_at=Greatest(
            F("updated_at"),
            Coalesce(Subquery(messages.values("created_at")[:1]), F("updated_at")),
            Coalesce(Subquery(versions.values("created_at")[:1]), F("updated_at")),
            Coalesce(Subquery(publications.values("updated_at")[:1]), F("updated_at")),
            output_field=DateTimeField(),
        ),
    )


def bucket_rows(rows, bucket):
    # Guard missing JSON keys so exclusion does not discard unassessed legacy rows.
    attention = (
        Q(status="NEEDS_CLARIFICATION")
        | Q(status="ERROR")
        | Q(status__in=["DRAFT", "READY", "PARTIAL"], scope_assessment__has_key="status", scope_assessment__status__in=["NEEDS_CLARIFICATION", "OUT_OF_SCOPE"])
    )
    if bucket == "clarify":
        return rows.filter(attention)
    if bucket == "consult":
        return rows.filter(status__in=["READY", "PARTIAL"], has_result=True).exclude(attention)
    if bucket == "active":
        return rows.filter(status__in=ACTIVE_STATUSES)
    return rows


class AnalysisTitleIn(Schema):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)


class AnalysisDeleteIn(Schema):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = False


@router.patch("/analyses/{analysis_id}/title")
@transaction.atomic
def rename_analysis(request, analysis_id: UUID, payload: AnalysisTitleIn):
    from .analysis_titles import analysis_title
    from .business_decisions import BUSY

    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id)
    if value.status in BUSY:
        raise HttpError(409, "Wait for the analysis to finish before renaming it.")
    title = " ".join(payload.title.split())
    if not title:
        raise HttpError(422, "Enter an analysis title.")
    value.display_title = title
    value.save(update_fields=["display_title"])
    return {"title": analysis_title(value)}


def analysis_summary(value):
    from .analysis_states import result_state
    from .api import request_dict

    data = request_dict(value)
    discussion = data.get("discussion") or {}
    waiting_ai = bool((discussion.get("job") or {}).get("waiting_reason")) if discussion.get("mode") == "discussion" else bool(value.latest_wait_reason or value.latest_run_wait_reason)
    return {
        **data,
        "href": f"/analyses/{value.pk}",
        "latest_activity_at": value.latest_activity_at,
        "latest_version_number": value.result_number,
        "has_result": value.has_result,
        "result_limits": value.result_limits or [],
        "stage": (value.progress[-1].get("label", "") if value.progress else "") if value.status in ACTIVE_STATUSES else "",
        "intent_resolved": value.intent_mode != "auto" or bool(value.understanding) or bool(value.result_number),
        "result_state": result_state(value.status, value.workflow, latest_status=value.result_status,
                                     waiting_ai=waiting_ai,
                                     published=value.published_latest,
                                     incomplete=bool(value.result_blocking),
                                     stale=bool(value.need_revised_at and value.result_created_at and value.need_revised_at > value.result_created_at),
                                     verification_unavailable=bool(value.result_blocking and value.result_database_status == "unavailable"),
                                     scope_rejected=value.scope_assessment.get("status") == "OUT_OF_SCOPE",
                                     scope_clarification=value.scope_assessment.get("status") == "NEEDS_CLARIFICATION"),
    }


@router.get("/analyses")
def list_analyses(
    request,
    q: str = "",
    workflow: Literal["all", "request", "question"] = "all",
    status: str = "",
    environment_id: int | None = None,
    bucket: Literal["all", "clarify", "consult", "active"] = "all",
    page: int = 1,
    page_size: int = 20,
):
    if not 1 <= page <= 1_000_000 or not 1 <= page_size <= 100 or len(q) > 500:
        raise HttpError(422, "Invalid analysis search or pagination.")
    if environment_id is not None and environment_id <= 0:
        raise HttpError(422, "Invalid environment filter.")
    if status and status not in Request.Status.values:
        raise HttpError(422, "Unknown analysis status.")
    from .discussion_access import visible

    rows = bucket_rows(visible(request, analysis_rows()), bucket)
    if workflow != "all":
        rows = rows.filter(workflow=workflow).filter(Q(intent_mode="explicit") | ~Q(understanding="") | Q(has_result=True))
    if status:
        rows = rows.filter(status=status)
    if environment_id:
        rows = rows.filter(environment_id=environment_id)
    if q.strip():
        text = q.strip()
        rows = rows.filter(
            Q(need__icontains=text) | Q(understanding__icontains=text)
            | Q(display_title__icontains=text)
            | Q(environment_name_snapshot__icontains=text) | Q(environment__name__icontains=text)
            | Q(versions__ticket__title__icontains=text)
            | Q(versions__explanation__title__icontains=text)
        ).distinct()
    rows = rows.order_by("-latest_activity_at", "-created_at", "id")
    total = rows.count()
    start = (page - 1) * page_size
    return {
        "items": [analysis_summary(value) for value in rows[start:start+page_size]],
        "total": total, "page": page, "page_size": page_size,
        "pages": ceil(total / page_size),
        "has_previous": page > 1, "has_next": start + page_size < total,
    }


@router.get("/analyses/overview")
def analysis_overview(request):
    from .discussion_access import visible

    rows = visible(request, analysis_rows()).order_by("-latest_activity_at", "-created_at", "id")
    sections = {}
    for bucket in ("clarify", "consult", "active"):
        selected = bucket_rows(rows, bucket)
        sections[bucket] = {
            "count": selected.count(),
            "items": [analysis_summary(value) for value in selected[:3]],
        }
    return {"sections": sections, "recent": [analysis_summary(value) for value in rows[:6]]}


@router.get("/analyses/{analysis_id}")
def get_analysis(request, analysis_id: UUID):
    from .api import request_dict

    value = get_object_or_404(Request.objects.select_related("environment", "source_question_version"), pk=analysis_id)
    if value.workflow == "question":
        from .question_actions import question_dict

        return question_dict(value, full=True)
    return request_dict(value, full=True)


@router.post("/analyses/{analysis_id}/need")
def update_analysis_need(request, analysis_id: UUID, payload: NeedRevisionIn):
    from .business_decisions import response_for
    from .discussion_access import actor
    from .need_revisions import revise_need

    return response_for(revise_need(analysis_id, payload, discussion_actor=actor(request)))


@router.post("/analyses/{analysis_id}/analyze")
def analyze_analysis(request, analysis_id: UUID):
    from .api import request_dict
    from .services import enqueue_analysis

    value = get_object_or_404(Request, pk=analysis_id)
    if value.discussion_state.get("enabled"):
        from .discussion import MessageIn, enqueue
        from .discussion_access import actor

        return request_dict(enqueue(value.pk, MessageIn(expected_revision=0), actor(request), initial=True), full=True)
    return request_dict(enqueue_analysis(value.pk), full=True)


@router.post("/analyses/{analysis_id}/attachments", response={201: dict})
def upload_analysis_attachment(request, analysis_id: UUID, file: File[UploadedFile]):
    from .services import add_attachment

    value = get_object_or_404(Request, pk=analysis_id)
    attachment = add_attachment(value.pk, file)
    return Status(201, {"id": str(attachment.pk), "name": attachment.name, "size": attachment.size})


@router.delete("/analyses/{analysis_id}")
@transaction.atomic
def delete_analysis(request, analysis_id: UUID, payload: AnalysisDeleteIn):
    """Remove a dossier from active views while retaining linked publication evidence."""
    if payload.confirmed is not True:
        raise HttpError(422, "Confirm deletion of this analysis.")
    # Use the unfiltered manager to make a repeated confirmation idempotent.
    value = get_object_or_404(Request.all_objects.select_for_update(), pk=analysis_id)
    if value.deleted_at:
        return {"status": "DELETED"}
    if value.status in ACTIVE_STATUSES or Job.objects.filter(
        kind__in=["analysis", "discussion"], target=str(value.pk), status__in=["QUEUED", "RUNNING"],
    ).exists() or StepExecution.objects.filter(
        job__kind="analysis", job__target=str(value.pk), status="RUNNING",
    ).exists() or any(job.payload.get("connection_ids") for job in Job.objects.filter(
        kind__in=["analysis", "discussion"], target=str(value.pk), status="CANCELLED",
    )):
        raise HttpError(409, "Cancel the analysis and wait for its agents to stop before deleting it.")
    if value.published_tickets.filter(status="PUBLISHING").exists():
        raise HttpError(409, "Wait for ticket publication to finish before deleting this analysis.")
    value.deleted_at = timezone.now()
    value.save(update_fields=["deleted_at"])
    return {"status": "DELETED"}
