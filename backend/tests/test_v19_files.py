"""Hostile uploads stay inert and cannot masquerade as supported document formats."""

import io
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.errors import HttpError

from core.environment_context import upload_resource
from core.file_validation import attachment_path
from core.models import GitConnection, Request, RequestAttachment
from core.secrets import encrypt
from core.services import add_attachment

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name,data", [
    ("image.png", b"<svg onload=alert(1) />"), ("document.pdf", b"MZ-executable"),
    ("notes.txt", b"\x7fELFbinary"), ("archive.txt", b"PK\x03\x04archive"),
    ("binary.md", b"hello\x00world"), ("archive.zip", b"PK\x03\x04archive"),
    ("macro.docm", b"PK\x03\x04macro"), ("empty.txt", b""),
])
def test_bad_upload_rejected_and_removed(environment, storage, name, data):
    item = Request.objects.create(environment=environment, need="Explain business behavior")
    with pytest.raises(HttpError):
        add_attachment(item.pk, SimpleUploadedFile(name, data))
    assert not item.attachments.exists()
    assert not list(storage.rglob("*.*"))


def test_content_type_is_observed_not_trusted(environment, storage):
    item = Request.objects.create(environment=environment, need="Explain business behavior")
    file = add_attachment(item.pk, SimpleUploadedFile("note.md", b"# Inert text", "text/html"))
    assert file.content_type == "text/plain"
    assert Path(file.path).name.startswith(str(file.pk))
    assert Path(file.path).stat().st_mode & 0o022 == 0


def test_stream_limit_does_not_trust_upload_size(environment, storage):
    item = Request.objects.create(environment=environment, need="Explain business behavior")
    class Oversized:
        name, size, content_type = "note.txt", 1, "text/plain"
        def chunks(self):
            for _ in range(26):
                yield b"x" * 1024 * 1024
    with pytest.raises(HttpError, match="25 MB"):
        add_attachment(item.pk, Oversized())
    assert not item.attachments.exists()


@pytest.mark.parametrize("entry", ["../outside.xml", "word/vbaProject.bin", "word/embeddings/data.bin"])
def test_docx_container_rejects_traversal_and_active_parts(environment, storage, entry):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("word/document.xml", "document")
        archive.writestr(entry, "hostile")
    item = Request.objects.create(environment=environment, need="Explain business behavior")
    with pytest.raises(HttpError):
        add_attachment(item.pk, SimpleUploadedFile("doc.docx", stream.getvalue()))


def test_docx_bomb_and_context_mime_spoof_are_rejected(environment, storage):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("word/document.xml", "x" * 2 * 1024 * 1024)
    item = Request.objects.create(environment=environment, need="Explain business behavior")
    with pytest.raises(HttpError):
        add_attachment(item.pk, SimpleUploadedFile("doc.docx", stream.getvalue()))
    with pytest.raises(HttpError):
        upload_resource(environment.pk, SimpleUploadedFile("fake.png", b"executable"), environment.context_revision)
    assert not environment.context_resources.exists()


def test_download_rejects_cross_request_path_and_symlink(environment, storage):
    first = Request.objects.create(environment=environment, need="Explain first behavior")
    second = Request.objects.create(environment=environment, need="Explain second behavior")
    file = add_attachment(first.pk, SimpleUploadedFile("note.txt", b"private"))
    file.request = second
    with pytest.raises(HttpError):
        attachment_path(file)
    file.request = first
    target = Path(file.path)
    target.unlink()
    target.symlink_to(storage / "outside")
    with pytest.raises(HttpError):
        attachment_path(file)


def test_configured_secret_in_attachment_is_rejected(environment, storage):
    GitConnection.objects.create(name="Private", provider="github", base_url="https://github.com", secret=encrypt("fixture-upload-private-token"))
    item = Request.objects.create(environment=environment, need="Explain business behavior")
    with pytest.raises(HttpError, match="credentials"):
        add_attachment(item.pk, SimpleUploadedFile("note.txt", b"fixture-upload-private-token"))
    assert RequestAttachment.objects.count() == 0
