"""Local retirement, fenced by existing jobs; never deletes external resources."""

import logging
import shutil
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from .models import (
    AISession,
    AnalysisResult,
    AnalysisRun,
    GeneratedArtifact,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
)


def cleanup_context(run):
    identifier = run.orchestration.get("cleanup_snapshot")
    if not identifier:
        return
    try:
        identifier = str(UUID(identifier))
        shared = (
            ResultVersion.all_objects.filter(context_snapshot__snapshot_id=identifier).exists()
            or AnalysisRun.all_objects.exclude(pk=run.pk)
            .filter(context_snapshot__snapshot_id=identifier)
            .exists()
        )
        if not shared:
            root = settings.DATA_DIR.resolve()
            path = root / "analysis-context" / str(UUID(str(run.request_id))) / identifier
            if path.is_symlink() or any(
                parent.is_symlink()
                for parent in path.parents
                if parent != root and parent.is_relative_to(root)
            ):
                raise ValueError("Invalid context directory")
            if path.exists():
                shutil.rmtree(path)
        AnalysisRun.all_objects.filter(pk=run.pk, deleted_at__isnull=False).update(orchestration={})
    except (OSError, ValueError):
        # Keep an owned cleanup pointer for the maintenance retry; no orphan
        # is silently forgotten, and shared evidence is never removed.
        logging.getLogger(__name__).warning("Retired analysis context cleanup deferred")


def delete_run(request_id, number):
    # Same lock order as completion: job, conversation, cycle. A cancelled job is
    # retained until its supervisor has observed the fence (never deleted here).
    initial = get_object_or_404(AnalysisRun.all_objects, request_id=request_id, number=number)
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=initial.job_id) if initial.job_id else None
        value = get_object_or_404(Request.all_objects.select_for_update(), pk=request_id)
        run = AnalysisRun.all_objects.select_for_update().get(pk=initial.pk)
        if run.deleted_at:
            return {"status": "DELETED"}
        if job and (job.status in {"QUEUED", "RUNNING"} or job.payload.get("connection_ids")):
            if value.analysis_protocol != "2.4":
                raise HttpError(409, "Stop this historical analysis before deleting it.")
            job.executions.exclude(status="DONE").update(
                status="CANCELLED", finished_at=timezone.now()
            )
            job.status, job.finished_at = "CANCELLED", timezone.now()
        if job:
            job.payload = {**job.payload, "delete_run_requested": True}
            job.save(update_fields=["payload", "status", "finished_at"])
        run.status = "CANCELLED" if job and job.status == "CANCELLED" else run.status
        run.save(update_fields=["status"])

    if job:
        from .step_execution import acknowledge_cancellation

        if job.status == "CANCELLED" and not acknowledge_cancellation(job):
            return {"status": "STOPPING"}
        sessions = (
            AISession.objects.filter(stepexecution__job=job)
            .exclude(pk=value.primary_session_id)
            .distinct()
        )
        contexts = [
            session.context_id
            for session in sessions
            if not session.stepexecution_set.exclude(job=job).exists()
        ]
        if contexts:
            from .agent import runtime_call

            try:
                released = runtime_call(
                    "/sessions/release",
                    {
                        "request_id": str(request_id),
                        "context_ids": [str(item) for item in contexts],
                    },
                    timeout=10,
                )
            except ValueError:
                return {"status": "STOPPING"}
            if released.get("released") is not True:
                return {"status": "STOPPING"}

    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=initial.job_id) if initial.job_id else None
        value = Request.all_objects.select_for_update().get(pk=request_id)
        run = AnalysisRun.all_objects.select_for_update().get(pk=initial.pk)
        if run.deleted_at:
            return {"status": "DELETED"}
        versions = list(ResultVersion.all_objects.filter(run=run))
        ids = [item.pk for item in versions]
        # Only cycle-owned messages are removed; independent exchanges remain.
        RequestMessage.objects.filter(
            request=value, version_id__in=ids, kind__in=["result", "error"]
        ).delete()
        RequestMessage.objects.filter(request=value, data__run_number=number).exclude(
            kind__in=["need", "discussion_reply", "ticket_publication"]
        ).delete()
        for version in versions:
            retained = (
                version.published_tickets.exists()
                or version.ticket_drafts.exists()
                or version.transferred_attachments.exists()
                or value.conversation_tickets.filter(source_version=version).exists()
                or Request.all_objects.filter(source_question_version=version).exists()
            )
            fields = {"deleted_at": timezone.now()}
            if not retained:
                GeneratedArtifact.objects.filter(version=version).delete()
                version.documents.all().delete()
                fields.update(
                    ticket={},
                    explanation={},
                    technical_summary="",
                    context_usage=[],
                    decisions_snapshot=[],
                    business_summary={},
                    evidence={},
                    context_snapshot={},
                    baseline=[],
                    database_snapshot={},
                )
            # Keep only the identifier/number when unreferenced. Numbers must
            # never be reused by future cycles or historical links.
            ResultVersion.all_objects.filter(pk=version.pk).update(**fields)
        if job:
            sessions = list(
                job.executions.exclude(session=None).values_list("session_id", flat=True)
            )
            job.executions.update(
                session=None,
                output={},
                instruction_snapshot={},
                skill_snapshot={},
                loaded_skills=[],
                owner="",
                process_id=None,
            )
            AISession.objects.filter(pk__in=sessions).exclude(pk=value.primary_session_id).exclude(
                stepexecution__isnull=False
            ).delete()
            job.payload, job.progress, job.error = {"delete_run_requested": True}, {}, ""
            job.save(update_fields=["payload", "progress", "error"])
        cleanup_snapshot = run.context_snapshot.get("snapshot_id")
        run.deleted_at = timezone.now()
        (
            run.steps,
            run.orchestration,
            run.context_snapshot,
            run.context_usage,
            run.error,
            run.warnings,
        ) = [], {}, {}, [], "", []
        if cleanup_snapshot:
            run.orchestration = {"cleanup_snapshot": cleanup_snapshot}
        run.save(
            update_fields=[
                "deleted_at",
                "steps",
                "orchestration",
                "context_snapshot",
                "context_usage",
                "error",
                "warnings",
            ]
        )
        latest = value.versions.order_by("-number").first()
        if latest:
            AnalysisResult.objects.filter(request=value).update(
                ticket=latest.ticket, markdown=latest.technical_summary
            )
        else:
            AnalysisResult.objects.filter(request=value).delete()
        active = Job.objects.filter(
            target=str(value.pk),
            kind__in=["analysis", "discussion"],
            status__in=["QUEUED", "RUNNING"],
        ).exists()
        if not active and not value.analysis_runs.filter(number__gt=number).exists():
            value.status, value.error, value.questions = "DISCUSSING", "", []
            value.discussion_state = {**value.discussion_state, "mode": "discussion"}
        value.save(update_fields=["status", "error", "questions", "discussion_state", "updated_at"])
    cleanup_context(run)
    return {"status": "DELETED"}


def finish_pending():
    """A closed browser must not abandon an acknowledged deletion request."""
    for run in AnalysisRun.objects.filter(job__payload__delete_run_requested=True)[:20]:
        delete_run(run.request_id, run.number)
    for run in AnalysisRun.all_objects.filter(
        deleted_at__isnull=False, orchestration__cleanup_snapshot__isnull=False
    )[:20]:
        cleanup_context(run)


@transaction.atomic
def remove_publication(identifier):
    row = get_object_or_404(PublishedTicket.objects.select_for_update(), pk=identifier)
    if row.removed_at:
        return {"status": "REMOVED"}
    if row.status != "PUBLISHED":
        raise HttpError(409, "Only confirmed publications can be removed from this history.")
    if any(item.get("status") == "TRANSFERRING" for item in row.attachment_delivery):
        raise HttpError(409, "Wait for attachment transfer to finish before removing this ticket.")
    RequestMessage.objects.filter(
        request_id=row.request_id, kind="ticket_publication", data__publication_id=str(row.pk)
    ).delete()
    # Keep destination, reference, identity and digest for duplicate prevention.
    # Other publications and their document ownership are deliberately untouched.
    PublishedTicket.objects.filter(pk=row.pk).update(
        removed_at=timezone.now(),
        body="",
        fields={},
        snapshot={},
        attachment_delivery=[],
        attempt_history=[],
    )
    return {"status": "REMOVED"}
