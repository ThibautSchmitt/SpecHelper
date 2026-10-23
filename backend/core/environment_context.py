"""Versioned environment documents and reproducible, lazily explored context."""

import codecs
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from .models import ContextResource, ContextResourceVersion, Environment

MAX_FILES = 20
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_INSTRUCTIONS = 4000
PREVIEW_LIMIT = 6000
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}


def reject_credentials(text):
    from .sensitive_data import configured_secrets

    if any(value in text for value in configured_secrets()):
        raise HttpError(422, "Keep configured credentials in the secure connection settings.")


def storage_root():
    # Separate from environment worktrees, which can be removed independently.
    return Path(settings.DATA_DIR) / "context-resources"


def checked_path(version):
    root = storage_root().resolve()
    path = Path(version.path)
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise HttpError(409, "The frozen context resource is unavailable.")
    if not path.is_file() or path.stat().st_size != version.size:
        raise HttpError(409, "The frozen context resource is unavailable.")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != version.sha256:
        raise HttpError(409, "The frozen context resource failed its integrity check.")
    return path


def version_dict(version, resource, preview=False, source=None):
    suffix = Path(version.filename).suffix.lower()
    value = {
        "id": str(resource.id),
        "name": resource.name,
        "enabled": resource.enabled,
        "filename": version.filename,
        "content_type": version.content_type,
        "size": version.size,
        "sha256": version.sha256,
        "version": version.version,
        "version_id": str(version.id),
        "created_at": resource.created_at.isoformat(),
        "updated_at": resource.updated_at.isoformat(),
        "agent_readable": suffix
        in TEXT_EXTENSIONS | {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".gif", ".webp"},
    }
    if preview:
        value.update(preview=None, preview_truncated=False)
    if suffix in TEXT_EXTENSIONS:
        try:
            with (source or checked_path(version)).open("rb") as stream:
                data = stream.read(PREVIEW_LIMIT * 4 + 4)
            decoder = codecs.getincrementaldecoder("utf-8")()
            text = decoder.decode(data, final=len(data) >= version.size)
            if "\x00" in text:
                raise UnicodeError("Binary document")
            if preview:
                value["preview"] = text[:PREVIEW_LIMIT]
                value["preview_truncated"] = len(text) > PREVIEW_LIMIT or version.size > len(data)
        except UnicodeError:
            value["agent_readable"] = False
    return value


def describe(environment):
    resources = environment.context_resources.filter(removed=False).prefetch_related("versions")
    return {
        "instructions": environment.context_instructions,
        "instructions_enabled": environment.instructions_enabled,
        "revision": environment.context_revision,
        "max_files": MAX_FILES,
        "max_file_size": MAX_FILE_SIZE,
        "resources": [
            version_dict(max(r.versions.all(), key=lambda v: v.version), r, True)
            for r in resources.order_by("created_at", "id")
            if r.versions.all()
        ],
    }


def locked_environment(environment_id, expected_revision):
    environment = get_object_or_404(Environment.objects.select_for_update(), pk=environment_id)
    if environment.context_revision != expected_revision:
        raise HttpError(409, "The environment context has changed. Refresh before editing.")
    return environment


def advance(environment):
    environment.context_revision += 1
    environment.save(
        update_fields=["context_revision", "context_instructions", "instructions_enabled"]
    )
    return describe(environment)


@transaction.atomic
def update_instructions(environment_id, instructions, enabled, expected_revision):
    environment = locked_environment(environment_id, expected_revision)
    if len(instructions) > MAX_INSTRUCTIONS or "\x00" in instructions:
        raise HttpError(422, "Context instructions must contain at most 4000 text characters.")
    reject_credentials(instructions)
    environment.context_instructions = instructions
    environment.instructions_enabled = enabled
    return advance(environment)


def store_upload(resource, upload):
    from .services import ALLOWED_EXTENSIONS

    name = Path(upload.name.replace("\\", "/")).name
    reject_credentials(name)
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise HttpError(422, "Invalid filename")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HttpError(422, "File format not allowed")
    if upload.size > MAX_FILE_SIZE:
        raise HttpError(422, "The maximum size is 25 MB")
    version_id = uuid.uuid4()
    directory = storage_root() / str(resource.id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (str(version_id) + Path(name).suffix.lower())
    digest, size = hashlib.sha256(), 0
    try:
        with path.open("xb") as stream:
            for chunk in upload.chunks():
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HttpError(422, "The maximum size is 25 MB")
                digest.update(chunk)
                stream.write(chunk)
        from .file_validation import inspect_file

        content_type = inspect_file(path, name)
        if Path(name).suffix.lower() in TEXT_EXTENSIONS:
            try:
                reject_credentials(path.read_text(encoding="utf-8"))
            except UnicodeError:
                pass
        path.chmod(0o444)
        number = (resource.versions.aggregate(last=Max("version"))["last"] or 0) + 1
        return ContextResourceVersion.objects.create(
            id=version_id,
            resource=resource,
            version=number,
            filename=name,
            content_type=content_type,
            size=size,
            sha256=digest.hexdigest(),
            path=str(path),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


@transaction.atomic
def upload_resource(environment_id, upload, expected_revision, resource_id=None):
    environment = locked_environment(environment_id, expected_revision)
    name = Path(upload.name.replace("\\", "/")).name
    reject_credentials(name)
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise HttpError(422, "Invalid filename")
    if resource_id:
        resource = get_object_or_404(
            ContextResource, pk=resource_id, environment=environment, removed=False
        )
    else:
        if environment.context_resources.filter(removed=False).count() >= MAX_FILES:
            raise HttpError(422, "A maximum of 20 context resources is allowed.")
        resource = ContextResource.objects.create(
            environment=environment, name=Path(upload.name.replace("\\", "/")).name[:255]
        )
    store_upload(resource, upload)
    resource.save(update_fields=["updated_at"])
    return advance(environment)


@transaction.atomic
def edit_resource(
    environment_id, resource_id, expected_revision, name=None, enabled=None, remove=False
):
    environment = locked_environment(environment_id, expected_revision)
    resource = get_object_or_404(
        ContextResource, pk=resource_id, environment=environment, removed=False
    )
    if name is not None:
        if not name.strip() or len(name) > 255 or any(ord(c) < 32 for c in name):
            raise HttpError(422, "Enter a context resource name of at most 255 characters.")
        resource.name = name.strip()
    if enabled is not None:
        resource.enabled = enabled
    if remove:
        resource.removed, resource.enabled = True, False
    resource.save()
    return advance(environment)


@transaction.atomic
def snapshot_environment(environment):
    environment = Environment.objects.select_for_update().get(pk=environment.pk)
    instructions = environment.context_instructions if environment.instructions_enabled else ""
    resources = []
    for resource in environment.context_resources.filter(enabled=True, removed=False).order_by(
        "id"
    ):
        version = resource.versions.order_by("-version").first()
        if version:
            resources.append(version_dict(version, resource, source=checked_path(version)))
    from .library import snapshot as library_snapshot

    return {
        "schema_version": 1,
        "environment": {
            "id": environment.id,
            "name": environment.name,
            "revision": environment.context_revision,
        },
        "instructions": {
            "text": instructions,
            "enabled": environment.instructions_enabled,
            "sha256": hashlib.sha256(instructions.encode()).hexdigest(),
        },
        "resources": resources,
        "library": library_snapshot(environment),
    }


def freeze_context(request, run=None, reuse=None):
    """Freeze active logical references; clarification can explicitly reuse its prior manifest."""
    import copy

    snapshot = (
        copy.deepcopy(reuse) if reuse is not None else snapshot_environment(request.environment)
    )
    from .sensitive_data import configured_secrets, redact

    snapshot["snapshot_id"] = str(uuid.uuid4())
    snapshot["dossier"] = {
        "request_id": str(request.id),
        "workflow": request.workflow,
        "category": request.category,
        "need": request.need,
        "answers": request.conversation,
        "baseline": request.baseline,
        "database": request.database_snapshot,
        "attachments": list(request.attachments.values("id", "name", "size", "content_type")),
    }
    snapshot["dossier"]["attachments"] = [
        {**item, "id": str(item["id"])} for item in snapshot["dossier"]["attachments"]
    ]
    snapshot = redact(snapshot, configured_secrets())
    snapshot.pop("sha256", None)
    snapshot["sha256"] = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    request.context_snapshot = snapshot
    request.save(update_fields=["context_snapshot"])
    if run is not None:
        run.context_snapshot = snapshot
        run.save(update_fields=["context_snapshot"])
    return snapshot


def materialize_context(snapshot, destination):
    """Copy verified immutable versions without consulting current resource activation."""
    import copy

    result = copy.deepcopy(snapshot)
    directory = Path(destination) / "context"
    directory.mkdir(parents=True, exist_ok=True)
    for entry in result.get("resources", []):
        version = get_object_or_404(
            ContextResourceVersion, pk=entry["version_id"], resource_id=entry["id"]
        )
        if version.sha256 != entry["sha256"] or version.version != entry["version"]:
            raise HttpError(409, "The frozen context resource failed its integrity check.")
        source = checked_path(version)
        relative = Path("context") / (str(version.id) + Path(version.filename).suffix.lower())
        target = Path(destination) / relative
        if target.exists():
            if (
                target.is_symlink()
                or hashlib.sha256(target.read_bytes()).hexdigest() != version.sha256
            ):
                raise HttpError(409, "The materialized context failed its integrity check.")
        else:
            temporary = directory / ("." + str(uuid.uuid4()))
            try:
                shutil.copyfile(source, temporary)
                temporary.chmod(0o444)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        entry["relative_path"] = str(relative)
    return result
