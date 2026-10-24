"""Question actions reuse the shared request queue and immutable result versions."""

from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from .creation_policy import automatic_comparison, creation_settings
from .models import (
    Environment,
    QuestionDocument,
    Request,
    RequestAttachment,
    RequestMessage,
    ResultVersion,
)
from .sensitive_data import configured_secrets, redact
from .services import add_attachment


def question(question_id, *, lock=False):
    queryset = Request.objects.select_related("environment")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    return get_object_or_404(queryset, pk=question_id, workflow="question")


def source_version(question_id, number):
    value = get_object_or_404(
        ResultVersion.objects.select_related("request", "run"),
        request_id=question_id,
        request__workflow="question",
        number=number,
    )
    if value.status not in {"READY", "PARTIAL"} or not value.explanation:
        raise HttpError(409, "A usable consolidated answer is required.")
    return value


@transaction.atomic
def create(environment_id, need, confrontation=False, category="general"):
    if not need.strip():
        raise HttpError(422, "Enter your question.")
    options = creation_settings()
    environment = get_object_or_404(Environment, pk=environment_id)
    value = Request.objects.create(
        workflow="question",
        analysis_protocol="2.4",
        environment=environment,
        environment_name_snapshot=environment.name,
        need=need.strip(),
        confrontation=automatic_comparison(options),
        category=category,
        language=options.language,
    )
    RequestMessage.objects.create(request=value, role="user", kind="need", content=value.need)
    return value


def question_dict(value, full=False):
    from .api import request_dict

    result = request_dict(value, full=full)
    result["workflow"] = "question"
    if full:
        result["derived_requests"] = [
            {
                "id": str(item.id),
                "need": item.need,
                "status": item.status,
                "source_version": item.source_question_version.number,
                "created_at": item.created_at,
            }
            for item in Request.objects.filter(source_question_version__request=value)
            .select_related("source_question_version")
            .order_by("created_at")
        ]
        result["latest_version"] = question_version_dict(value.versions.order_by("-number").first())
        result.pop("ticket", None)
        result["markdown"] = (
            result["latest_version"]["answer_markdown"] if result["latest_version"] else None
        )
    return result


def question_version_dict(version):
    if version is None:
        return None
    from .api import version_dict

    result = version_dict(version)
    result.pop("ticket", None)
    result.pop("goal_markdown", None)
    result["explanation"] = version.explanation
    artifact = version.artifacts.filter(name="answer.md").first()
    result["answer_markdown"] = artifact.content if artifact else ""
    result["markdown"] = result["answer_markdown"]
    result["artifacts"] = (
        {
            "answer.md": f"/api/questions/{version.request_id}/versions/{version.number}/artifacts/answer.md"
        }
        if artifact
        else {}
    )
    result["documents"] = [document_dict(document) for document in version.documents.all()]
    return result


def document_dict(document):
    version = document.source_version
    return {
        "id": str(document.id),
        "kind": document.kind,
        "markdown": document.markdown,
        "source_question_id": str(version.request_id),
        "source_version": version.number,
        "baseline": version.baseline,
        "language": version.language,
        "created_at": document.created_at,
        "download_url": (
            f"/api/questions/{version.request_id}/versions/{version.number}"
            f"/documents/{document.id}/download"
        ),
    }


@transaction.atomic
def create_document(question_id, number, kind):
    from .question_outputs import render_document

    version = source_version(question_id, number)
    if kind not in {"business", "technical", "mixed"}:
        raise HttpError(422, "Unknown documentation format.")
    secrets = configured_secrets()
    try:
        markdown = render_document(
            redact(version.explanation, secrets),
            redact(version.baseline, secrets),
            kind,
            version.language,
        )
    except ValueError as exc:
        raise HttpError(
            422, "This answer cannot be exported safely. Continue the question to revise it."
        ) from exc
    markdown += (
        f"\n---\n\n[Question {version.request_id}](/questions/{version.request_id})"
        f" · v{version.number}\n"
    )
    return QuestionDocument.objects.create(
        source_version=version, kind=kind, markdown=redact(markdown, secrets)
    )


def transfer_preview(question_id, number):
    from .question_outputs import render_transfer

    version = source_version(question_id, number)
    secrets = configured_secrets()
    try:
        content = render_transfer(
            redact(version.request.need, secrets),
            redact(version.explanation, secrets),
            redact(version.baseline, secrets),
            version=version.number,
            language=version.language,
            request_id=str(version.request_id),
            created_at=version.created_at,
        )
    except ValueError as exc:
        raise HttpError(
            422, "This answer cannot be exported safely. Continue the question to revise it."
        ) from exc
    return {
        "name": f"question-{version.request_id}-v{version.number}-context.md",
        "content": redact(content, secrets),
        "source_question_id": str(version.request_id),
        "source_version": version.number,
        "environment_id": version.request.environment_id,
        "baseline": redact(version.baseline, secrets),
        "language": version.language,
    }


@transaction.atomic
def create_request(
    question_id,
    number,
    environment_id,
    need,
    confrontation=False,
    include_context=True,
    category="auto",
):
    if not need.strip():
        raise HttpError(422, "Describe the requested change explicitly.")
    version = source_version(question_id, number)
    options = creation_settings()
    environment = get_object_or_404(Environment, pk=environment_id)
    preview = transfer_preview(question_id, number) if include_context else None
    value = Request.objects.create(
        workflow="request",
        analysis_protocol="2.4",
        source_question_version=version,
        environment=environment,
        environment_name_snapshot=environment.name,
        need=need.strip(),
        confrontation=automatic_comparison(options),
        category=category,
        language=options.language,
    )
    RequestMessage.objects.create(request=value, role="user", kind="need", content=value.need)
    if preview:
        attachment = add_attachment(
            value.id,
            SimpleUploadedFile(preview["name"], preview["content"].encode(), "text/markdown"),
        )
        attachment.source_question_version = version
        attachment.save(update_fields=["source_question_version"])
    return value


@transaction.atomic
def remove_attachment(request_id, attachment_id, workflow):
    value = get_object_or_404(Request.objects.select_for_update(), pk=request_id, workflow=workflow)
    if value.status != Request.Status.DRAFT:
        raise HttpError(409, "Attachments are frozen after launch")
    attachment = get_object_or_404(RequestAttachment, pk=attachment_id, request=value)
    path = Path(attachment.path)
    root = (settings.MEDIA_ROOT / str(value.id) / "attachments").resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise HttpError(409, "The attachment is unavailable.")
    attachment.delete()
    transaction.on_commit(lambda: path.unlink(missing_ok=True))
