import re
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from ninja.errors import HttpError

from .models import (
    AnalysisRun,
    Job,
    Request,
    RequestAttachment,
    RequestMessage,
)


def queue_run(request, continuing=False, changed_decision_keys=None):
    if request.analysis_protocol == "2.3":
        request.confrontation = True
    if not request.messages.exists():
        RequestMessage.objects.create(
            request=request, role="user", kind="need", content=request.need
        )
    job = Job.objects.create(
        kind="analysis",
        target=str(request.id),
        payload={
            "analysis_protocol": request.analysis_protocol,
            "decision_revision": request.decision_revision,
            "changed_decision_keys": changed_decision_keys or [],
        },
    )
    number = (request.analysis_runs.aggregate(last=Max("number"))["last"] or 0) + 1
    from .environment_context import freeze_context

    reuse = (
        request.context_snapshot
        if (
            request.status == Request.Status.NEEDS_CLARIFICATION
            or not request.environment_id
            or changed_decision_keys
        )
        else None
    )
    run = AnalysisRun.objects.create(request=request, job=job, number=number)
    freeze_context(request, run, reuse=reuse)
    request.status = Request.Status.CONTINUING_CONVERSATION if continuing else Request.Status.QUEUED
    request.error, request.progress = "", []
    request.save()
    return request


def require_session_connection(request):
    from .providers import ensure_connections

    ensure_connections()


ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".log",
}


@transaction.atomic
def enqueue_analysis(
    request_id,
    answers=None,
    choices=None,
    expected_decision_revision=None,
    confirm_changes=False,
    analysis_protocol=None,
):
    request = (
        Request.objects.select_for_update(of=("self",))
        .select_related("environment__database")
        .get(pk=request_id)
    )
    changed_decision_keys = []
    if answers is None and choices is None:
        if request.status != Request.Status.DRAFT:
            raise HttpError(409, "This request has already been started")
        require_session_connection(request)
        environment = request.environment
        if environment is None:
            raise HttpError(409, "This environment was deleted. Create a new request.")
        if environment.status != "READY":
            raise HttpError(409, "The environment must be synchronized")
        repos = list(environment.repositories.all())
        if not repos or any(not re.fullmatch(r"[a-f0-9]{40}", r.sha) for r in repos):
            raise HttpError(409, "The environment baseline is incomplete")
        from .git_sources import repository_snapshot

        request.baseline = [repository_snapshot(repository) for repository in repos]
        request.environment_name_snapshot = environment.name
        request.database_snapshot = (
            {"id": environment.database_id, "name": environment.database.name}
            if environment.database_id
            else {}
        )
        from .providers import bind_session, candidates

        available = candidates()
        if available:
            bind_session(request, available[0])
    else:
        if request.status != Request.Status.NEEDS_CLARIFICATION:
            raise HttpError(409, "This request is not awaiting an answer")
        from .business_decisions import accept_answers

        answers, changed_decision_keys = accept_answers(
            request, answers or {}, choices, expected_decision_revision, confirm_changes
        )
        request.conversation += [{"questions": request.questions, "answers": answers}]
        require_session_connection(request)
        RequestMessage.objects.create(
            request=request,
            role="user",
            kind="answer",
            content="\n\n".join(q["question"] + "\n" + answers[q["id"]] for q in request.questions),
            data={"questions": request.questions, "answers": answers},
        )
        request.questions = []
    if analysis_protocol == "2.3":
        request.analysis_protocol = "2.3"
    return queue_run(request, changed_decision_keys=changed_decision_keys)


@transaction.atomic
def continue_conversation(request_id, message, expected_version, analysis_protocol=None):
    request = Request.objects.select_for_update().get(pk=request_id)
    from .business_decisions import assert_editable

    assert_editable(request)
    if request.status not in {"READY", "PARTIAL", "ERROR"}:
        raise HttpError(409, "Wait for the result or answer the pending questions.")
    latest = request.versions.order_by("-number").first()
    if not latest or latest.number != expected_version:
        raise HttpError(409, "The result has changed. Refresh the page before continuing.")
    if not message.strip():
        raise HttpError(422, "Enter your message.")
    require_session_connection(request)
    RequestMessage.objects.create(
        request=request, role="user", kind="followup", content=message.strip(), version=latest
    )
    request.questions = []
    if analysis_protocol == "2.3":
        request.analysis_protocol = "2.3"
    return queue_run(request, continuing=True)


def add_attachment(request_id, upload):
    with transaction.atomic():
        request = Request.objects.select_for_update().get(pk=request_id)
        if request.status != Request.Status.DRAFT:
            raise HttpError(409, "Attachments are frozen after launch")
        name = Path(upload.name.replace("\\", "/")).name
        if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
            raise HttpError(422, "Invalid filename")
        if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise HttpError(422, "File format not allowed")
        if upload.size > 25 * 1024 * 1024:
            raise HttpError(422, "The maximum size is 25 MB")
        if request.attachments.count() >= 20:
            raise HttpError(422, "A maximum of 20 attachments is allowed")
        attachment_id = uuid.uuid4()
        directory = settings.MEDIA_ROOT / str(request.id) / "attachments"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (str(attachment_id) + Path(name).suffix.lower())
        try:
            with path.open("xb") as stream:
                size = 0
                for chunk in upload.chunks():
                    size += len(chunk)
                    if size > 25 * 1024 * 1024:
                        raise HttpError(422, "The maximum size is 25 MB")
                    stream.write(chunk)
            from .environment_context import reject_credentials
            from .file_validation import inspect_file

            content_type = inspect_file(path, name)
            reject_credentials(name)
            if path.suffix in {".txt", ".md", ".csv", ".json", ".log"}:
                reject_credentials(path.read_text(encoding="utf-8-sig"))
            path.chmod(0o444)
            return RequestAttachment.objects.create(
                id=attachment_id,
                request=request,
                name=name,
                path=str(path),
                content_type=content_type,
                size=size,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
