"""Environment context stays optional, isolated and reproducible across edits."""

import hashlib
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from ninja.errors import HttpError

from core import environment_context as context
from core.models import ContextResource, ContextResourceVersion, Environment, Request

pytestmark = pytest.mark.django_db


def upload(environment, content=b"Architecture reference", filename="architecture.md", revision=1):
    return context.upload_resource(
        environment.id, SimpleUploadedFile(filename, content, "text/plain"), revision
    )


def test_instruction_toggle_and_revision_guards(environment, storage):
    value = context.update_instructions(environment.id, "Preserve API compatibility.", True, 1)
    assert value["revision"] == 2
    assert value["resources"] == []
    with pytest.raises(HttpError, match="changed"):
        context.update_instructions(environment.id, "stale", True, 1)
    environment.refresh_from_db()
    before = context.snapshot_environment(environment)
    assert before["instructions"]["text"] == "Preserve API compatibility."
    context.update_instructions(environment.id, "Changed", False, 2)
    after = context.snapshot_environment(environment)
    assert after["instructions"]["text"] == ""
    assert before["instructions"]["text"] == "Preserve API compatibility."


def test_replacement_keeps_frozen_versions_and_environment_deletion(environment, storage, tmp_path):
    value = upload(environment)
    resource = ContextResource.objects.get()
    old = resource.versions.get()
    environment.refresh_from_db()
    snapshot = context.snapshot_environment(environment)
    context.upload_resource(
        environment.id,
        SimpleUploadedFile("architecture.md", b"New reference"),
        value["revision"],
        resource.id,
    )
    old.refresh_from_db()
    assert old.sha256 == hashlib.sha256(b"Architecture reference").hexdigest()
    assert resource.versions.count() == 2
    context.edit_resource(environment.id, resource.id, 3, remove=True)
    assert context.snapshot_environment(environment)["resources"] == []
    materialized = context.materialize_context(snapshot, tmp_path / "run")
    path = tmp_path / "run" / materialized["resources"][0]["relative_path"]
    assert path.read_bytes() == b"Architecture reference"
    environment.delete()
    resource.refresh_from_db()
    assert resource.environment_id is None
    assert context.checked_path(old).read_bytes() == b"Architecture reference"


def test_disabled_documents_are_retained_and_not_snapshotted(environment, storage):
    value = upload(environment)
    resource = ContextResource.objects.get()
    context.edit_resource(environment.id, resource.id, value["revision"], enabled=False)
    assert context.snapshot_environment(environment)["resources"] == []
    resource.refresh_from_db()
    assert resource.versions.count() == 1
    context.edit_resource(environment.id, resource.id, 3, name="Conventions", enabled=True)
    current = context.snapshot_environment(environment)
    assert current["resources"][0]["name"] == "Conventions"


def test_preview_is_bounded_and_binary_text_is_reported(environment, storage):
    value = upload(environment, b"x" * 40000)
    resource = value["resources"][0]
    assert len(resource["preview"]) == 6000
    assert resource["preview_truncated"] is True
    assert resource["agent_readable"] is True
    value = upload(environment, b"\xff\x00", "broken.txt", revision=2)
    assert value["resources"][1]["preview"] is None
    assert value["resources"][1]["agent_readable"] is False
    value = upload(environment, "é".encode() * 20000, "utf8.txt", revision=3)
    assert value["resources"][2]["agent_readable"] is True


def test_snapshot_has_no_document_body_or_host_paths(environment, storage):
    upload(environment, b"SENSITIVE LONG BODY" * 5000)
    snapshot = context.snapshot_environment(environment)
    assert "SENSITIVE LONG BODY" not in str(snapshot)
    assert str(storage) not in str(snapshot)
    assert snapshot["resources"][0]["sha256"]
    request = Request.objects.create(environment=environment, need="Inspect the export.")
    assert context.freeze_context(request) == request.context_snapshot
    frozen = request.context_snapshot
    context.update_instructions(environment.id, "Later changes", True, 2)
    resumed = context.freeze_context(request, reuse=frozen)
    assert resumed["resources"] == frozen["resources"]
    assert resumed["instructions"] == frozen["instructions"]


@pytest.mark.parametrize("filename", ["program.exe", "run.sh", "module.py", "bad\x00.md"])
def test_existing_attachment_type_and_filename_guards(environment, storage, filename):
    with pytest.raises(HttpError):
        upload(environment, filename=filename)
    assert ContextResource.objects.count() == 0


def test_stream_limit_and_document_count(environment, storage, monkeypatch):
    monkeypatch.setattr(context, "MAX_FILE_SIZE", 5)
    with pytest.raises(HttpError, match="25 MB"):
        upload(environment)
    monkeypatch.setattr(context, "MAX_FILE_SIZE", 25 * 1024 * 1024)
    monkeypatch.setattr(context, "MAX_FILES", 1)
    upload(environment)
    with pytest.raises(HttpError, match="20 context"):
        upload(environment, revision=2)
    assert ContextResource.objects.count() == 1


def test_tampered_and_cross_environment_resources_are_rejected(environment, storage):
    upload(environment)
    version = ContextResourceVersion.objects.get()
    path = context.checked_path(version)
    path.chmod(0o644)
    path.write_text("Tampered")
    with pytest.raises(HttpError, match="unavailable"):
        context.snapshot_environment(environment)
    other = Environment.objects.create(name="Other")
    with pytest.raises(Exception) as error:
        context.edit_resource(other.id, version.resource_id, 1, enabled=False)
    assert getattr(error.value, "status_code", 404) == 404


def test_context_api_guards_metadata_download_and_soft_removal(environment, storage):
    client = Client()
    prefix = f"/api/environments/{environment.id}/context"
    assert client.get(prefix).json()["revision"] == 1
    response = client.post(
        prefix + "/resources",
        {
            "file": SimpleUploadedFile("reference.md", b"Use active implementation."),
            "expected_revision": "1",
        },
    )
    assert response.status_code == 200, response.content
    value = response.json()
    resource = value["resources"][0]
    assert "path" not in resource
    resource_url = prefix + "/resources/" + resource["id"]
    download = client.get(resource_url + "/versions/" + resource["version_id"] + "/download")
    assert b"".join(download.streaming_content) == b"Use active implementation."
    response = client.patch(
        resource_url,
        data={"enabled": False, "expected_revision": 2},
        content_type="application/json",
    )
    assert response.status_code == 200
    response = client.delete(resource_url + "?expected_revision=3")
    assert response.json()["resources"] == []
    assert ContextResourceVersion.objects.count() == 1
    assert (
        client.get(
            prefix
            + "/resources/"
            + str(uuid.uuid4())
            + "/versions/"
            + resource["version_id"]
            + "/download"
        ).status_code
        == 404
    )
