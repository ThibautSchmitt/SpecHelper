"""Presentation, consent, reliability and native attachment delivery contracts."""

import json
import uuid
from unittest.mock import Mock

import pytest
from ninja.errors import HttpError
from ninja.testing import TestClient
from test_ticket_providers import transport as _transport
from test_ticket_publication import publication_context as _publication_context

from core.models import (
    AnalysisRun,
    GeneratedArtifact,
    PublishedTicket,
    RequestAttachment,
    TicketPublicationDraft,
)
from core.ticket_api import router
from core.ticket_providers import GitLabProvider, GLPIProvider, JiraProvider, NetworkUncertain
from core.ticket_publication import preview, publish

pytestmark = pytest.mark.django_db
publication_context = _publication_context
transport = _transport


def options(**values):
    return {
        "ticket_format": "standard",
        "include_business_analysis": False,
        "include_technical_analysis": False,
        "include_attachments": False,
        "attachment_ids": [],
        "include_goal": False,
        "template_id": "",
        "issue_type": "",
        **values,
    }


def attachment(version, settings):
    root = settings.MEDIA_ROOT / str(version.request_id) / "attachments"
    root.mkdir(parents=True)
    path = root / "notes.txt"
    path.write_text("Reviewed source document")
    return RequestAttachment.objects.create(
        request=version.request,
        name="notes.txt",
        path=str(path),
        content_type="text/plain",
        size=path.stat().st_size,
    )


def test_standard_default_five_parts_and_optional_details_preserve_goal(publication_context):
    version, connector, provider, _ = publication_context
    version.ticket.update(
        proposed_solution="Reuse the export",
        technical_impact=["Existing service"],
        risks=["Keep read-only source access"],
    )
    version.technical_summary = "Technical details " * 100
    version.business_summary = {
        "current": "Current business state",
        "desired": "Desired business outcome",
        "gap": "Detailed business gap",
    }
    GeneratedArtifact.objects.create(
        version=version, name="goal.md", content="Exhaustive goal details"
    )
    short = preview(version, connector, "42", presentation=options())
    assert short["body"].startswith("# Export contracts")
    assert all(
        "## " + label in short["body"]
        for label in ("Description", "Business summary", "Technical summary", "Proposed solution")
    )
    assert "Keep read-only source access" in short["body"]
    assert "Detailed business gap" not in short["body"]
    assert len(short["body"].split()) < 170
    detailed = preview(
        version,
        connector,
        "42",
        presentation=options(include_business_analysis=True, include_technical_analysis=True),
    )
    assert "Detailed business gap" in detailed["body"]
    assert len(detailed["body"]) > len(short["body"])
    assert version.artifacts.get(name="goal.md").content == "Exhaustive goal details"
    provider.create.assert_not_called()
    assert AnalysisRun.objects.count() == 0


def test_frozen_analysis_intent_suggests_real_template_without_reanalysis(publication_context):
    version, connector, provider, _ = publication_context
    run = AnalysisRun.objects.create(
        request=version.request, number=1, status="READY", orchestration={"inferred_intent": "bug"}
    )
    type(version).objects.filter(pk=version.pk).update(run=run)
    version.refresh_from_db()
    provider.options.return_value = {
        "revision": "templates",
        "templates": [
            {"id": "actual-bug", "name": "Bug report"},
            {"id": "actual-feature", "name": "Feature request"},
        ],
        "issue_types": [],
        "fields": [],
        "labels": [],
        "assignees": [],
        "template_body": "## Project fields",
    }
    result = preview(version, connector, "42", presentation=options(ticket_format=""))
    assert result["template_id"] == "actual-bug"
    assert not result["requires_template_choice"]
    assert len(result["templates"]) == 2
    assert AnalysisRun.objects.count() == 1
    provider.create.assert_not_called()


def test_real_templates_recompose_and_required_fields_remain_in_standard(publication_context):
    version, connector, provider, payload = publication_context

    def native_options(project, template_id="", issue_type=""):
        return {
            "revision": "rev-" + template_id,
            "templates": [{"id": "bug", "name": "Bug"}, {"id": "feature", "name": "Feature"}],
            "issue_types": [{"id": "1", "name": "Task"}],
            "fields": [{"id": "cost", "label": "Cost center", "required": True, "type": "text"}],
            "template_body": "## Context\n\n" + template_id,
            "labels": [],
            "assignees": [],
        }

    provider.options.side_effect = native_options
    initial = preview(version, connector, "42", presentation=options(ticket_format="project"))
    assert initial["requires_template_choice"]
    assert len(initial["templates"]) == 2
    bug = preview(
        version,
        connector,
        "42",
        "bug",
        "1",
        options(ticket_format="project", template_id="bug", issue_type="1"),
    )
    feature = preview(
        version,
        connector,
        "42",
        "feature",
        "1",
        options(ticket_format="project", template_id="feature", issue_type="1"),
    )
    assert bug["draft_id"] == feature["draft_id"]
    assert bug["template_id"] == "bug" and feature["template_id"] == "feature"
    assert feature["fields"][0]["required"]
    standard = preview(version, connector, "42", presentation=options(issue_type="1"))
    assert standard["fields"][0]["id"] == "cost"
    with pytest.raises(HttpError, match="required"):
        publish(
            version,
            connector,
            {
                **payload,
                **options(issue_type="1"),
                "options_revision": "rev-",
                "labels": [],
                "assignees": [],
            },
        )
    provider.create.assert_not_called()


def test_draft_edits_survive_reload_with_version_environment_and_sha(publication_context):
    version, connector, _, payload = publication_context
    client = TestClient(router)
    endpoint = f"/requests/{version.request_id}/versions/1/publication-draft"
    first = client.get(endpoint, query_params={"connector_id": connector.pk, "project": "42"})
    assert first.status_code == 200
    initial = first.json()
    edited = {
        **{
            key: payload[key]
            for key in (
                "connector_id",
                "project",
                "title",
                "body",
                "fields",
                "labels",
                "assignees",
                "options_revision",
            )
        },
        **options(),
        "draft_id": initial["draft_id"],
        "draft_revision": initial["draft_revision"],
    }
    response = client.put(endpoint, json=edited)
    assert response.status_code == 200, response.content
    result = client.get(
        endpoint, query_params={"connector_id": connector.pk, "project": "42"}
    ).json()
    assert result["body"] == payload["body"]
    assert result["title"] == payload["title"]
    assert result["defaults"]["labels"] == ["bug"]
    assert result["labels"] == [{"id": "bug", "name": "Bug"}]
    assert result["version_id"] == str(version.pk)
    assert result["environment_name"] == version.environment_name
    assert result["baseline"] == version.baseline
    assert TicketPublicationDraft.objects.count() == 1
    conflict = client.put(endpoint, json=edited)
    assert conflict.status_code == 409
    edited.update(
        draft_revision=result["draft_revision"], idempotency_key=str(uuid.uuid4()), confirmed=True
    )
    delivered = client.post(f"/requests/{version.request_id}/versions/1/publications", json=edited)
    assert delivered.status_code == 200, delivered.content
    record = PublishedTicket.objects.get()
    assert record.body == result["body"]
    assert record.snapshot["version_id"] == str(version.pk)
    assert record.external_reference == response.json()["publication_reference"]
    from core.ticket_providers import render_body

    assert (
        render_body(record.snapshot, result, record.external_reference) == result["rendered_body"]
    )


def test_ready_label_cannot_hide_unverified_material_evidence(publication_context):
    from core.ticket_presentation import publication_blockers

    version, _, _, _ = publication_context
    version.evidence = {"blocking": False, "claims": [{"status": "unverified", "material": True}]}
    assert version.status == "READY"
    assert "A material conclusion lacks the required verification." in publication_blockers(version)


def test_partial_draft_is_consultable_but_export_cannot_unlock_publication(publication_context):
    version, connector, provider, payload = publication_context
    version.status = "PARTIAL"
    version.evidence = {
        "blocking": True,
        "limitations": ["Verifier unavailable: quota exhausted"],
        "claims": [],
    }
    result = preview(version, connector, "42", presentation=options())
    assert result["body"]
    assert not result["publication_allowed"]
    assert "Verifier unavailable: quota exhausted" in result["publication_blockers"]
    with pytest.raises(HttpError, match="blocked"):
        publish(version, connector, payload)
    provider.create.assert_not_called()


def test_ready_label_without_independent_checks_is_not_sufficient(publication_context):
    version, connector, provider, payload = publication_context
    version.request.analysis_protocol = "2.4"
    result = preview(version, connector, "42", presentation=options())
    assert not result["publication_allowed"]
    assert "Missing independent check: Verifier" in result["publication_blockers"]
    with pytest.raises(HttpError, match="blocked"):
        publish(version, connector, payload)
    provider.create.assert_not_called()


def test_attachment_opt_in_subset_goal_and_immutable_hash(publication_context, settings):
    version, connector, provider, payload = publication_context
    original = attachment(version, settings)
    GeneratedArtifact.objects.create(version=version, name="goal.md", content="Detailed goal")
    short = preview(version, connector, "42", presentation=options())
    assert not short["include_attachments"] and short["selected_attachments"] == []
    assert {row["kind"] for row in short["available_attachments"]} == {"original", "goal"}
    no_files = publish(version, connector, {**payload, **options()})
    assert no_files.snapshot["selected_attachments"] == []
    provider.attach.assert_not_called()
    # A separate analysis version can explicitly transfer only its original file.
    from core.models import ResultVersion

    second = ResultVersion.objects.create(
        request=version.request,
        number=2,
        environment_name=version.environment_name,
        ticket=version.ticket,
    )
    chosen = options(include_attachments=True, attachment_ids=[str(original.pk)])
    reviewed = preview(second, connector, "42", presentation=chosen)
    assert reviewed["selected_attachments"][0]["kind"] == "original"
    provider.attach.return_value = {"id": "uploaded-1"}
    provider.create.return_value = {
        "external_id": "124",
        "external_key": "#2",
        "url": "https://gitlab.example/team/project/-/issues/2",
    }
    sent = publish(second, connector, {**payload, **chosen, "idempotency_key": uuid.uuid4()})
    assert sent.attachment_delivery[0]["status"] == "TRANSFERRED"
    assert provider.attach.call_count == 1
    assert (
        sent.snapshot["selected_attachments"][0]["sha256"]
        == reviewed["selected_attachments"][0]["sha256"]
    )
    publish(second, connector, {**payload, **chosen, "idempotency_key": uuid.uuid4()})
    assert provider.attach.call_count == 1


def test_attachment_timeout_keeps_issue_and_never_reuploads(publication_context, settings):
    version, connector, provider, payload = publication_context
    original = attachment(version, settings)
    provider.attach.side_effect = NetworkUncertain("synthetic lost response")
    selected = {**payload, **options(include_attachments=True, attachment_ids=[str(original.pk)])}
    record = publish(version, connector, selected)
    assert record.status == "PUBLISHED"
    assert record.attachment_delivery[0]["status"] == "UNCERTAIN"
    assert "issue exists" in record.attachment_delivery[0]["error"]
    publish(version, connector, selected)
    assert provider.create.call_count == provider.attach.call_count == 1


def test_other_request_attachment_and_unsupported_github_never_transfer(
    publication_context, settings
):
    version, connector, provider, payload = publication_context
    with pytest.raises(HttpError, match="cannot be transferred"):
        publish(
            version,
            connector,
            {**payload, **options(include_attachments=True, attachment_ids=[str(uuid.uuid4())])},
        )
    original = attachment(version, settings)
    connector.platform = "github"
    shown = preview(version, connector, "42", presentation=options())
    assert not shown["available_attachments"][0]["transferable"]
    with pytest.raises(HttpError, match="cannot be transferred"):
        publish(
            version,
            connector,
            {**payload, **options(include_attachments=True, attachment_ids=[str(original.pk)])},
        )
    provider.create.assert_not_called()
    provider.attach.assert_not_called()


def test_native_attachment_protocols_use_only_explicit_bytes(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("core.ticket_providers.decrypt", lambda value: value)
    connection = SimpleNamespace(
        base_url="https://tickets.example",
        secret="fixture-only",
        username="user",
        api_version="v1",
        app_token="",
    )
    metadata = {"name": "proof.txt", "mime": "text/plain", "size": 5}
    gitlab = GitLabProvider(connection)
    gitlab.request = Mock(side_effect=[{"id": 12, "url": "/uploads/ab12/proof.txt"}, {"id": 13}])
    assert gitlab.attach("42", "7", metadata, b"proof")["id"] == "12"
    assert gitlab.request.call_args_list[0].kwargs["files"]["file"] == (
        "proof.txt",
        b"proof",
        "text/plain",
    )
    assert gitlab.request.call_args_list[1].args[1].endswith("/issues/7/notes")
    jira = JiraProvider(connection)
    jira.request = Mock(side_effect=[{"enabled": True, "uploadLimit": 1000}, [{"id": "99"}]])
    assert jira.attach("42", "APP-7", metadata, b"proof")["id"] == "99"
    assert jira.request.call_args.kwargs["extra_headers"] == {"X-Atlassian-Token": "no-check"}
    glpi = GLPIProvider.__new__(GLPIProvider)
    glpi.request = Mock(side_effect=[{"id": 5}, {"id": 6}])
    assert glpi.attach("42", "7", metadata, b"proof")["id"] == "5"
    manifest = json.loads(glpi.request.call_args_list[0].kwargs["data"]["uploadManifest"])
    assert manifest["input"]["_filename"] == ["proof.txt"]
    assert glpi.request.call_args_list[1].kwargs["data"]["input"] == {
        "documents_id": 5,
        "itemtype": "Ticket",
        "items_id": 7,
    }


def test_jira_attachment_size_denial_prevents_upload(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("core.ticket_providers.decrypt", lambda value: value)
    jira = JiraProvider(
        SimpleNamespace(base_url="https://tickets.example", secret="fixture-only", username="user")
    )
    jira.request = Mock(return_value={"enabled": True, "uploadLimit": 2})
    with pytest.raises(ValueError, match="exceeds"):
        jira.attach("42", "APP-7", {"name": "file.txt", "mime": "text/plain", "size": 3}, b"abc")
    assert jira.request.call_count == 1


def test_actual_multipart_transport_preserves_mime_and_bytes(transport):
    from types import SimpleNamespace

    calls = transport(
        {
            ("POST", "/api/v4/projects/42/uploads"): (
                201,
                {"id": 11, "url": "/uploads/ab12/proof.txt"},
            ),
            ("POST", "/api/v4/projects/42/issues/7/notes"): (201, {"id": 12}),
        }
    )
    provider = GitLabProvider(
        SimpleNamespace(base_url="https://tickets.example", secret="dedicated-ticket-credential")
    )
    provider.attach("42", "7", {"name": "proof.txt", "mime": "text/plain", "size": 5}, b"proof")
    upload = calls[0]
    assert upload.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b'filename="proof.txt"' in upload.content
    assert b"Content-Type: text/plain" in upload.content
    assert b"\r\nproof\r\n" in upload.content
    assert upload.headers["PRIVATE-TOKEN"] == "dedicated-ticket-credential"
    assert json.loads(calls[1].content)["body"] == "[proof.txt](/uploads/ab12/proof.txt)"


def test_stale_inflight_attachment_is_uncertain_and_not_retried(publication_context, settings):
    from datetime import timedelta

    from django.utils import timezone

    from core.ticket_publication import publication_dict

    version, connector, provider, payload = publication_context
    original = attachment(version, settings)
    selected = {**payload, **options(include_attachments=True, attachment_ids=[str(original.pk)])}
    provider.attach.return_value = {"id": "uploaded-1"}
    record = publish(version, connector, selected)
    PublishedTicket.objects.filter(pk=record.pk).update(
        attachment_delivery=[
            {"id": str(original.pk), "name": original.name, "status": "TRANSFERRING"}
        ],
        updated_at=timezone.now() - timedelta(seconds=120),
    )
    record.refresh_from_db()
    assert publication_dict(record)["attachment_delivery"][0]["status"] == "UNCERTAIN"
    publish(version, connector, selected)
    assert provider.create.call_count == provider.attach.call_count == 1


def test_attachment_bytes_changed_since_preview_require_new_review(publication_context, settings):
    version, connector, provider, payload = publication_context
    original = attachment(version, settings)
    presentation = options(include_attachments=True, attachment_ids=[str(original.pk)])
    reviewed = preview(version, connector, "42", presentation=presentation)
    from pathlib import Path

    path = Path(original.path)
    original_bytes = path.read_bytes()
    path.write_bytes(b"X" * len(original_bytes))
    submitted = {
        **payload,
        **presentation,
        "title": reviewed["title"],
        "body": reviewed["body"],
        "labels": [],
        "assignees": [],
        "draft_id": reviewed["draft_id"],
    }
    with pytest.raises(HttpError, match="exact ticket draft"):
        publish(version, connector, submitted)
    provider.create.assert_not_called()
    provider.attach.assert_not_called()


def test_draft_reference_allows_safe_rejected_retry_without_duplicate_issue(publication_context):
    from core.ticket_providers import TicketProviderError

    version, connector, provider, payload = publication_context
    presentation = options()
    reviewed = preview(version, connector, "42", presentation=presentation)
    submitted = {
        **payload,
        **presentation,
        "title": reviewed["title"],
        "body": reviewed["body"],
        "labels": [],
        "assignees": [],
        "draft_id": reviewed["draft_id"],
    }
    provider.create.side_effect = TicketProviderError(
        "Ticket platform denied authentication or permission"
    )
    rejected = publish(version, connector, submitted)
    assert rejected.status == "ERROR"
    provider.create.side_effect = None
    accepted = publish(version, connector, {**submitted, "idempotency_key": uuid.uuid4()})
    assert accepted.status == "PUBLISHED"
    assert accepted.pk == rejected.pk
    assert PublishedTicket.objects.count() == 1


@pytest.mark.parametrize("language,heading", [("en", "Business summary"), ("fr", "Résumé métier")])
def test_standard_language_and_separate_goal_consent(publication_context, language, heading):
    version, connector, provider, payload = publication_context
    version.language = language
    GeneratedArtifact.objects.create(
        version=version, name="goal.md", content="Detailed implementation constraints"
    )
    selected = options(include_attachments=True, include_goal=True)
    reviewed = preview(version, connector, "42", presentation=selected)
    assert "## " + heading in reviewed["body"]
    assert reviewed["selected_attachments"][0]["kind"] == "goal"
    assert reviewed["attachment_ids"] == []
    provider.attach.return_value = {"id": "goal-upload"}
    record = publish(version, connector, {**payload, **selected})
    assert record.attachment_delivery[0]["status"] == "TRANSFERRED"
    assert provider.attach.call_args.args[2]["name"] == "goal.md"
    assert provider.attach.call_args.args[3] == b"Detailed implementation constraints"


def test_historical_api_reconciliation_keeps_original_digest(publication_context):
    version, connector, provider, payload = publication_context
    provider.create.side_effect = NetworkUncertain("synthetic lost response")
    uncertain = publish(version, connector, payload)
    assert uncertain.status == "UNCERTAIN"
    provider.find.return_value = {
        "external_id": "123",
        "external_key": "#1",
        "url": "https://gitlab.example/team/project/-/issues/1",
    }
    from core.models import ResultVersion

    ResultVersion.objects.filter(pk=version.pk).update(status="PARTIAL")
    submitted = {**payload, "idempotency_key": str(payload["idempotency_key"])}
    response = TestClient(router).post(
        f"/requests/{version.request_id}/versions/1/publications", json=submitted
    )
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "PUBLISHED"
    assert response.json()["id"] == str(uncertain.pk)
    assert provider.create.call_count == 1


def test_denied_attachment_permission_blocks_issue_creation(
    publication_context, settings, monkeypatch
):
    version, connector, provider, payload = publication_context
    original = attachment(version, settings)
    denied = Mock()
    denied.attachment_policy.return_value = {"enabled": False, "max_bytes": 0}
    monkeypatch.setattr("core.ticket_providers.provider_for", lambda connector: denied)
    with pytest.raises(HttpError, match="cannot be transferred"):
        publish(
            version,
            connector,
            {**payload, **options(include_attachments=True, attachment_ids=[str(original.pk)])},
        )
    provider.create.assert_not_called()
    provider.attach.assert_not_called()
