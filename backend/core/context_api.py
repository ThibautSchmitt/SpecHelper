"""Administration of optional, versioned environment reference resources."""

from uuid import UUID

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile
from pydantic import ConfigDict, Field

from . import environment_context as actions
from .models import AnalysisRun, ContextResourceVersion, Environment

router = Router(tags=["Environment context"])


class InstructionsIn(Schema):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(max_length=4000)
    instructions_enabled: bool
    expected_revision: int = Field(ge=1)
    official_references: list[dict] | None = Field(default=None, max_length=12)


class ResourceIn(Schema):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None


@router.get("/environments/{environment_id}/context")
def context(request, environment_id: int):
    return actions.describe(get_object_or_404(Environment, pk=environment_id))


@router.put("/environments/{environment_id}/context")
def update_context(request, environment_id: int, payload: InstructionsIn):
    return actions.update_instructions(
        environment_id,
        payload.instructions,
        payload.instructions_enabled,
        payload.expected_revision,
        payload.official_references,
    )


@router.post("/environments/{environment_id}/context/resources")
def upload_context(
    request, environment_id: int, file: File[UploadedFile], expected_revision: Form[int]
):
    return actions.upload_resource(environment_id, file, expected_revision)


@router.patch("/environments/{environment_id}/context/resources/{resource_id}")
def update_resource(request, environment_id: int, resource_id: UUID, payload: ResourceIn):
    return actions.edit_resource(
        environment_id, resource_id, payload.expected_revision, payload.name, payload.enabled
    )


@router.post("/environments/{environment_id}/context/resources/{resource_id}/versions")
def replace_resource(
    request,
    environment_id: int,
    resource_id: UUID,
    file: File[UploadedFile],
    expected_revision: Form[int],
):
    return actions.upload_resource(environment_id, file, expected_revision, resource_id)


@router.delete("/environments/{environment_id}/context/resources/{resource_id}")
def remove_resource(request, environment_id: int, resource_id: UUID, expected_revision: int):
    return actions.edit_resource(environment_id, resource_id, expected_revision, remove=True)


@router.get(
    "/environments/{environment_id}/context/resources/{resource_id}/versions/{version_id}/download"
)
def download_resource(request, environment_id: int, resource_id: UUID, version_id: UUID):
    version = get_object_or_404(
        ContextResourceVersion,
        pk=version_id,
        resource_id=resource_id,
        resource__environment_id=environment_id,
    )
    response = FileResponse(
        actions.checked_path(version).open("rb"),
        as_attachment=True,
        filename=version.filename,
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@router.get("/requests/{request_id}/runs/{run_number}/context/{version_id}/download")
def download_frozen_resource(request, request_id: UUID, run_number: int, version_id: UUID):
    run = get_object_or_404(AnalysisRun, request_id=request_id, number=run_number)
    entry = next(
        (
            item
            for item in run.context_snapshot.get("resources", [])
            if item["version_id"] == str(version_id)
        ),
        None,
    )
    if entry is None:
        from ninja.errors import HttpError

        raise HttpError(404, "This resource is not part of the frozen analysis context.")
    version = get_object_or_404(ContextResourceVersion, pk=version_id, sha256=entry["sha256"])
    response = FileResponse(
        actions.checked_path(version).open("rb"),
        as_attachment=True,
        filename=version.filename,
        content_type="application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
