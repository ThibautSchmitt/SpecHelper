"""Office inspection is bounded; SQL attachments are documents, never statements to execute."""

import io
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.errors import HttpError

from core import environment_context
from core.models import Job, Request
from core.services import add_attachment

pytestmark = pytest.mark.django_db


def workbook(extra=None, types=None):
    stream = io.BytesIO()
    rows = {
        "[Content_Types].xml": types
        or '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Facts" sheetId="1"/></sheets></workbook>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Reference</t></is></c><c r="B1"><v>42</v></c></row></sheetData></worksheet>',
    }
    rows.update(extra or {})
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in rows.items():
            archive.writestr(name, value)
    return stream.getvalue()


@pytest.mark.parametrize(
    "name,data,mime",
    [
        (
            "facts.xlsx",
            workbook(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "notes.SQL",
            b"\xef\xbb\xbf-- Notes fictives\nCREATE TABLE must_not_execute(id integer);\nSELECT 42;\n",
            "text/plain",
        ),
    ],
)
def test_supported_formats_round_trip_in_conversations(
    client, environment, storage, name, data, mime
):
    value = client.post(
        "/api/analyses",
        {"environment_id": environment.pk, "need": "Read the attached project reference."},
        content_type="application/json",
    ).json()
    response = client.post(
        f"/api/analyses/{value['id']}/attachments",
        {"file": SimpleUploadedFile(name, data, "text/html")},
    )
    assert response.status_code == 201, response.content
    attachment = Request.objects.get(pk=value["id"]).attachments.get()
    assert attachment.content_type == mime
    assert (
        Path(attachment.path).read_bytes() == data
        and Path(attachment.path).stat().st_mode & 0o222 == 0
    )
    download = client.get(f"/api/questions/{value['id']}/attachments/{attachment.pk}")
    assert b"".join(download.streaming_content) == data
    assert download["X-Content-Type-Options"] == "nosniff"
    assert not Job.objects.filter(target=value["id"]).exists()
    from django.db import connection

    assert "must_not_execute" not in connection.introspection.table_names()


@pytest.mark.parametrize(
    "name,data", [("facts.xlsx", workbook()), ("notes.sql", b"-- specification\nSELECT 42;\n")]
)
def test_supported_environment_documents_are_versioned_and_readable(
    environment, storage, name, data
):
    result = environment_context.upload_resource(
        environment.pk, SimpleUploadedFile(name, data), environment.context_revision
    )
    resource = result["resources"][0]
    assert resource["agent_readable"] is True
    if name.endswith(".sql"):
        version = environment.context_resources.get().versions.get()
        assert (
            environment_context.version_dict(version, version.resource, preview=True)["preview"]
            == data.decode()
        )
    frozen = environment_context.snapshot_environment(environment)
    assert frozen["resources"][0]["filename"] == name


@pytest.mark.parametrize(
    "entry",
    [
        "../escape.xml",
        "xl/vbaProject.bin",
        "xl/activeX/control.bin",
        "xl/embeddings/package.bin",
        "xl/externalLinks/externalLink1.xml",
        "xl/macrosheets/sheet1.xml",
        "xl/dialogsheets/sheet1.xml",
        "xl/connections.xml",
    ],
)
def test_active_or_escaping_workbooks_are_rejected_without_orphans(environment, storage, entry):
    value = Request.objects.create(environment=environment, need="Read reference")
    with pytest.raises(HttpError):
        add_attachment(value.pk, SimpleUploadedFile("hostile.xlsx", workbook({entry: "unsafe"})))
    assert not value.attachments.exists() and not list(storage.rglob("*.xlsx"))


@pytest.mark.parametrize(
    "data",
    [
        b"not an Office archive",
        workbook({"xl/worksheets/large.xml": "x" * 2 * 1024 * 1024}),
        workbook(types="application/vnd.ms-excel.sheet.macroEnabled.main+xml"),
    ],
)
def test_workbook_signature_bomb_and_macro_content_type_are_rejected(environment, storage, data):
    value = Request.objects.create(environment=environment, need="Read reference")
    with pytest.raises(HttpError):
        add_attachment(value.pk, SimpleUploadedFile("fake.xlsx", data))
    assert not value.attachments.exists()


@pytest.mark.parametrize(
    "data", [b"SELECT\x00binary", b"\x7fELFbinary", b"PK\x03\x04archive", b"\xff\xfe\x00"]
)
def test_sql_extension_does_not_allow_binary_content(environment, storage, data):
    value = Request.objects.create(environment=environment, need="Read reference")
    with pytest.raises(HttpError):
        add_attachment(value.pk, SimpleUploadedFile("fake.sql", data))
    assert not value.attachments.exists()


def test_malformed_xlsx_compression_is_a_validation_error(environment, storage):
    data = bytearray(workbook())
    for signature, offset in [(b"PK\x03\x04", 8), (b"PK\x01\x02", 10)]:
        index = data.index(signature)
        data[index + offset : index + offset + 2] = (99).to_bytes(2, "little")
    value = Request.objects.create(environment=environment, need="Read reference")
    with pytest.raises(HttpError):
        add_attachment(value.pk, SimpleUploadedFile("unsupported.xlsx", bytes(data)))
    assert not value.attachments.exists()
