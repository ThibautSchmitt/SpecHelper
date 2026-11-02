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


@pytest.mark.parametrize("language", ["en", "fr"])
def test_reports_reuse_frozen_sources_by_audience_without_new_investigation(
    source_message, frozen_code, environment, storage, monkeypatch, language
):
    from copy import deepcopy

    from core import environment_context
    from core.analysis_evidence import ReliabilityReport
    from core.question_actions import create_document

    value, _, receipt = source_message
    _, sha = frozen_code
    environment_context.upload_resource(environment.pk, SimpleUploadedFile("policy.md", b"Original retained policy", "text/plain"), 1)
    document_version = ContextResourceVersion.objects.get()
    snapshot = environment_context.snapshot_environment(environment)
    baseline = [{"repository":"fixture/project", "sha":sha, "branch":"main"}]
    snapshot["dossier"] = {"baseline":baseline}
    code = {"kind":"git", "repository":"fixture/project", "commit":sha,
            "path":"rules.py", "line_start":2, "line_end":3, "excerpt":"FIRST = 1\nCHECKED = True"}
    evidence = ReliabilityReport.model_validate({
        "claims":[{"id":"rule", "statement":"The rule remains unverified.", "kind":"unknown",
                   "status":"unverified", "scope":{"sample_limits":"Static inspection only."}, "sources":[code, {"kind":"sql", "query_id":"rejected-query"}]}],
        "database":{"status":"checked", "checks":[receipt, {**receipt,"query_id":"rejected-query", "status":"rejected", "sql":"SELECT rejected_statement"}]},
        "limitations":["No runtime behavior was verified."],
    }).model_dump()
    explanation = {"title":"Rule behavior", "summary":"The rule describes eligibility.",
                   "response":"Technical response mentioning `FIRST`.",
                   "business_explanation":"Eligible cases follow the rule.",
                   "technical_explanation":"The flag is checked by the caller.",
                   "references":[{"repository":"fixture/project", "path":"rules.py"}],
                   "evidence":evidence}
    saved_evidence = deepcopy(evidence)
    saved_evidence["web_references"] = [{"reference_id":"web-rule", "url":"https://example.org/rule", "title":"Official rule", "text":"Recorded page preview"}]
    version = ResultVersion.objects.create(request=value, number=1, status="PARTIAL", language=language,
        baseline=baseline, context_snapshot=snapshot, context_usage=[{"version_id":str(document_version.pk),"status":"observed"}],
        explanation=explanation, evidence=saved_evidence)
    # A later environment edit must not replace a source selected by this cycle.
    environment.refresh_from_db()
    environment_context.upload_resource(environment.pk, SimpleUploadedFile("policy.md", b"Later policy", "text/plain"), environment.context_revision, document_version.resource_id)
    value.need = "A different later subject"
    value.save()
    before_jobs = Job.objects.count()
    monkeypatch.setattr("core.discussion.runtime_call", lambda *a, **k: pytest.fail("No AI during report export"))
    business = create_document(value.pk, 1, "business")
    technical = create_document(value.pk, 1, "technical")
    mixed = create_document(value.pk, 1, "mixed")
    assert "FIRST = 1" not in business.markdown and "SELECT COUNT" not in business.markdown
    assert sha not in business.markdown and "Technical response" not in business.markdown
    assert "policy.md" in business.markdown and "https://example.org/rule" in business.markdown
    for document in (technical, mixed):
        assert "FIRST = 1\nCHECKED = True" in document.markdown and sha in document.markdown
        assert receipt["sql"] in document.markdown and "Original retained policy" in document.markdown
        assert "Later policy" not in document.markdown and "rejected_statement" not in document.markdown
        assert "rejected-query" not in document.markdown
        assert "Recorded page preview" in document.markdown
    for document in (business, technical, mixed):
        assert "No runtime behavior was verified." in document.markdown
        assert "Static inspection only." in document.markdown
        assert ("Non vérifié" if language == "fr" else "Unverified") in document.markdown
        assert document.source_version_id == version.pk
        assert "A different later subject" not in document.markdown
    assert Job.objects.count() == before_jobs
    version.refresh_from_db()
    assert version.explanation == explanation and version.evidence == saved_evidence
    original_export = technical.markdown
    monkeypatch.setattr("core.conversation_sources.code_excerpt", lambda *a: ("", "The frozen source excerpt is unavailable."))
    technical.refresh_from_db()
    assert technical.markdown == original_export
    unavailable = create_document(value.pk, 1, "technical")
    assert "FIRST = 1" not in unavailable.markdown
    assert ("indisponible" if language == "fr" else "unavailable") in unavailable.markdown


def test_report_sources_do_not_execute_or_promote_untrusted_source_text():
    from core.report_sources import render_sources

    sources = [
        {"kind":"web", "id":"web-quote", "title":"Rule <script>bad()</script>", "url":"https://example.org/rule", "excerpt":"A recorded rule."},
        {"kind":"document", "id":"document", "title":"policy.md", "excerpt":"```\n<script>bad()</script>\n```", "note":"Preview from the retained document; the exact passage used was not recorded."},
        {"kind":"sql", "id":"failed", "status":"unavailable", "sql":"SELECT hidden_statement"},
    ]
    business = render_sources(sources, "business")
    technical = render_sources(sources, "technical")
    assert "> A recorded rule." in business
    assert "<script>" not in business
    assert "````\n```\n<script>bad()</script>\n```\n````" in technical
    assert "does not by itself verify" in business and "does not by itself verify" in technical
    assert "hidden_statement" not in business + technical
    assert "exact passage used was not recorded" in business + technical
