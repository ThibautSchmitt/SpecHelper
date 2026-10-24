"""Question workflow routes share request services while keeping their intent explicit."""

from typing import Literal
from uuid import UUID

from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import File, Router, Schema
from ninja.files import UploadedFile
from ninja.responses import Status
from pydantic import ConfigDict, Field

from . import question_actions as actions
from .clarification_schema import AnswersIn
from .file_validation import attachment_path
from .models import GeneratedArtifact, QuestionDocument, Request, RequestAttachment
from .services import add_attachment, continue_conversation, enqueue_analysis

router = Router(tags=["Questions"])


class QuestionIn(Schema):
    model_config = ConfigDict(extra="forbid")
    environment_id: int
    need: str = Field(min_length=1, max_length=30000)
    confrontation: bool = False
    category: Literal["general", "technical", "functional", "architecture"] = "general"


class ContinuationIn(Schema):
    message: str = Field(min_length=1, max_length=30000)
    expected_version: int = Field(ge=1)


class DocumentIn(Schema):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["business", "technical", "mixed"]


class TransferIn(QuestionIn):
    need: str = Field(min_length=10, max_length=30000)
    source_version: int = Field(ge=1)
    include_context: bool = True
    category: Literal["auto", "feature", "bug", "documentation"] = "auto"


def markdown_response(content, filename):
    response = HttpResponse(content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/questions")
def questions(request):
    return [
        actions.question_dict(value)
        for value in Request.objects.filter(workflow="question")
        .select_related("environment")
        .order_by("-created_at")[:100]
    ]


@router.post("/questions", response={201: dict})
def create_question(request, payload: QuestionIn):
    value = actions.create(
        payload.environment_id, payload.need, payload.confrontation, payload.category
    )
    return Status(201, actions.question_dict(value, full=True))


@router.get("/questions/{question_id}")
def get_question(request, question_id: UUID):
    return actions.question_dict(actions.question(question_id), full=True)


@router.post("/questions/{question_id}/analyze")
def analyze_question(request, question_id: UUID):
    actions.question(question_id)
    return actions.question_dict(enqueue_analysis(question_id, analysis_protocol="2.4"), full=True)


@router.post("/questions/{question_id}/cancel")
def cancel_question_analysis(request, question_id: UUID):
    from .step_execution import cancel_analysis

    actions.question(question_id)
    return actions.question_dict(cancel_analysis(question_id), full=True)


@router.post("/questions/{question_id}/retry")
def retry_question_analysis(request, question_id: UUID):
    from .step_execution import retry_analysis

    actions.question(question_id)
    return actions.question_dict(retry_analysis(question_id), full=True)


@router.post("/questions/{question_id}/answers")
def answer_question(request, question_id: UUID, payload: AnswersIn):
    actions.question(question_id)
    return actions.question_dict(
        enqueue_analysis(
            question_id,
            payload.answers,
            payload.choices,
            payload.expected_decision_revision,
            payload.confirm_changes,
            analysis_protocol="2.4",
        ),
        full=True,
    )


@router.post("/questions/{question_id}/continue")
def continue_question(request, question_id: UUID, payload: ContinuationIn):
    actions.question(question_id)
    value = continue_conversation(
        question_id, payload.message, payload.expected_version, analysis_protocol="2.4"
    )
    return actions.question_dict(value, full=True)


@router.post("/questions/{question_id}/attachments", response={201: dict})
def upload_attachment(request, question_id: UUID, file: File[UploadedFile]):
    actions.question(question_id)
    attachment = add_attachment(question_id, file)
    return Status(201, {"id": str(attachment.id), "name": attachment.name, "size": attachment.size})


@router.get("/questions/{question_id}/attachments/{attachment_id}")
def download_attachment(request, question_id: UUID, attachment_id: UUID):
    actions.question(question_id)
    attachment = get_object_or_404(RequestAttachment, request_id=question_id, pk=attachment_id)
    response = FileResponse(
        attachment_path(attachment).open("rb"),
        as_attachment=True,
        filename=attachment.name,
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.delete("/questions/{question_id}/attachments/{attachment_id}")
def delete_question_attachment(request, question_id: UUID, attachment_id: UUID):
    actions.remove_attachment(question_id, attachment_id, "question")
    return {"status": "DELETED"}


@router.get("/questions/{question_id}/versions/{number}")
def get_version(request, question_id: UUID, number: int):
    return actions.question_version_dict(actions.source_version(question_id, number))


@router.get("/questions/{question_id}/versions/{number}/artifacts/{name}")
def download_answer(request, question_id: UUID, number: int, name: Literal["answer.md"]):
    version = actions.source_version(question_id, number)
    artifact = get_object_or_404(GeneratedArtifact, version=version, name=name)
    return markdown_response(artifact.content, "answer.md")


@router.get("/questions/{question_id}/versions/{number}/documents")
def documents(request, question_id: UUID, number: int):
    version = actions.source_version(question_id, number)
    return [actions.document_dict(value) for value in version.documents.all()]


@router.post("/questions/{question_id}/versions/{number}/documents", response={201: dict})
def create_document(request, question_id: UUID, number: int, payload: DocumentIn):
    document = actions.create_document(question_id, number, payload.kind)
    return Status(201, actions.document_dict(document))


@router.get("/questions/{question_id}/versions/{number}/documents/{document_id}/download")
def download_document(request, question_id: UUID, number: int, document_id: UUID):
    version = actions.source_version(question_id, number)
    document = get_object_or_404(QuestionDocument, pk=document_id, source_version=version)
    return markdown_response(document.markdown, f"question-v{number}-{document.kind}.md")


@router.get("/questions/{question_id}/versions/{number}/transfer")
def transfer_preview(request, question_id: UUID, number: int):
    return actions.transfer_preview(question_id, number)


@router.post("/questions/{question_id}/requests", response={201: dict})
def create_request(request, question_id: UUID, payload: TransferIn):
    from .api import request_dict

    value = actions.create_request(
        question_id,
        payload.source_version,
        payload.environment_id,
        payload.need,
        payload.confrontation,
        payload.include_context,
        payload.category,
    )
    return Status(201, request_dict(value, full=True))
