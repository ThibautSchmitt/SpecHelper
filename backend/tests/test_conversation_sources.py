"""Disclosure reads saved receipts and frozen blobs, never reruns an investigation."""

import subprocess

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from core.conversation_sources import code_excerpt
from core.models import ContextResourceVersion, Job, Request, RequestMessage, ResultVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def source_message(environment):
    value = Request.objects.create(environment=environment, workflow="question", need="Explain playlist counts.")
    receipt = {"query_id":"sql-"+"a"*32+"-"+"b"*12, "sql":"SELECT COUNT(*) FROM tracks", "status":"checked", "row_count":1, "truncated":False, "checked_at":"2026-11-01T12:00:00Z"}
    message = RequestMessage.objects.create(request=value, role="assistant", kind="discussion_reply", content="Counts from the database.", data={"revision":1,"session_pk":7,"observations":{"database_checks":[receipt]}})
    Job.objects.create(kind="discussion", target=str(value.pk), status="DONE", payload={"revision":1,"session_pk":7,"snapshot":{"dossier":{"baseline":[]}}})
    return value, message, receipt


def url(value, message):
    return f"/api/analyses/{value.pk}/messages/{message.pk}/sources"


def test_sql_disclosure_reads_the_actual_receipt_without_starting_work(client, source_message, monkeypatch):
    value, message, receipt = source_message
    before = Job.objects.count()
    monkeypatch.setattr("core.discussion.runtime_call", lambda *a, **k: pytest.fail("No inference during disclosure"))
    response = client.get(url(value, message))
    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["id"] == receipt["query_id"] and source["sql"] == receipt["sql"]
    assert source["row_count"] == 1 and Job.objects.count() == before
    message.refresh_from_db()
    assert message.data["observations"]["database_checks"] == [receipt]


@pytest.fixture
def frozen_code(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.run(["git","-C",str(root),*args],check=True,capture_output=True,text=True).stdout.strip()
    git("init")
    git("config","user.email","fixture@example.org")
    git("config","user.name","Fixture")
    (root / "rules.py").write_text("\nFIRST = 1\nCHECKED = True\n")
    git("add","rules.py")
    git("commit","-m","Fixture frozen source")
    sha = git("rev-parse","HEAD")
    (root / "rules.py").write_text("LATER_UNVERIFIED_CHANGE = True\n")
    monkeypatch.setattr("core.git.mirror_path", lambda row:root)
    return root, sha


def test_code_excerpt_keeps_original_lines_and_never_moves_workspace(frozen_code):
    root, sha = frozen_code
    baseline = [{"repository":"fixture/project","sha":sha}]
    source = {"repository":"fixture/project","commit":sha,"path":"rules.py","line_start":2,"line_end":3}
    excerpt, note = code_excerpt(source, baseline)
    assert excerpt == "FIRST = 1\nCHECKED = True" and not note
    assert (root / "rules.py").read_text() == "LATER_UNVERIFIED_CHANGE = True\n"
    assert not code_excerpt({**source,"path":"../../secret"}, baseline)[0]
    assert not code_excerpt({**source,"commit":"b"*40}, baseline)[0]
    assert not code_excerpt({**source,"path":".env"}, baseline)[0]


def test_version_disclosure_uses_stored_code_and_web_evidence(client, source_message, frozen_code):
    value, _, receipt = source_message
    _, sha = frozen_code
    git = {"kind":"git","repository":"fixture/project","commit":sha,"path":"rules.py","line_start":2,"line_end":3}
    web = {"kind":"web","reference_id":"web-fixture","excerpt":"The exact recorded passage."}
    version = ResultVersion.objects.create(request=value, number=1, context_snapshot={"dossier":{"baseline":[{"repository":"fixture/project","sha":sha}]}},
        evidence={"claims":[{"sources":[git,web]}],"database":{"checks":[receipt]},"web_references":[{"reference_id":"web-fixture","url":"https://example.org/reference","title":"Public fixture reference","text":"Before. The exact recorded passage. After.","consulted_at":"2026-11-01T12:00:00Z"}]})
    records = client.get(f"/api/analyses/{value.pk}/versions/{version.number}/sources").json()["sources"]
    code = next(source for source in records if source["kind"] == "git")
    assert code["excerpt"] == "FIRST = 1\nCHECKED = True"
    page = next(source for source in records if source["kind"] == "web")
    assert page["excerpt"] == "The exact recorded passage." and page["url"] == "https://example.org/reference"


def test_cited_code_resolves_against_the_discussion_jobs_frozen_manifest(client, source_message, frozen_code):
    value, message, _ = source_message
    _, sha = frozen_code
    message.content = "See `rules.py:2-3`."
    message.save()
    job = Job.objects.get(target=str(value.pk))
    job.payload["snapshot"] = {"dossier":{"baseline":[{"repository":"fixture/project","sha":sha}]}}
    job.save()
    records = client.get(url(value,message)).json()["sources"]
    assert next(source for source in records if source["kind"] == "git")["excerpt"] == "FIRST = 1\nCHECKED = True"


def test_document_preview_uses_the_read_version_not_a_later_replacement(client, source_message, environment, storage):
    from core import environment_context

    value, message, _ = source_message
    environment_context.upload_resource(environment.pk, SimpleUploadedFile("rules.md", b"Frozen document passage", "text/plain"), 1)
    version = ContextResourceVersion.objects.get()
    snapshot = environment_context.snapshot_environment(environment)
    job = Job.objects.get(target=str(value.pk))
    job.payload["snapshot"] = snapshot
    job.save()
    message.data["observations"]["context_usage"] = [{"version_id":str(version.pk),"status":"observed"}]
    message.save()
    environment.refresh_from_db()
    environment_context.upload_resource(environment.pk, SimpleUploadedFile("rules.md", b"Later replacement", "text/plain"), environment.context_revision, version.resource_id)
    records = client.get(url(value,message)).json()["sources"]
    document = next(source for source in records if source["kind"] == "document")
    assert document["excerpt"] == "Frozen document passage" and str(version.pk) in document["url"]
    assert "exact passage" in document["note"]


def test_missing_or_foreign_sources_fail_closed(client, source_message):
    value, message, _ = source_message
    other = Request.objects.create(need="Other conversation")
    assert client.get(url(other,message)).status_code == 404
    value.deleted_at = timezone.now()
    value.save()
    assert client.get(url(value,message)).status_code == 404


def test_source_disclosure_redacts_configured_credentials(client, source_message, monkeypatch):
    value, message, _ = source_message
    message.data["observations"]["database_checks"][0]["sql"] = "SELECT 'private-test-credential'"
    message.save()
    monkeypatch.setattr("core.conversation_sources.configured_secrets",lambda:["private-test-credential"])
    response = client.get(url(value,message))
    assert "private-test-credential" not in response.content.decode() and "[REDACTED]" in response.content.decode()
