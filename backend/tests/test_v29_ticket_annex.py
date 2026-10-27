"""Reviewed Mermaid annexes require explicit consent and supported transfer options."""

import uuid

import pytest
from ninja.errors import HttpError
from ninja.testing import TestClient
from test_ticket_publication import publication_context as _publication_context
from test_v25_tickets import options
from test_v29_diagrams import claim, proposal, reviews

from core.diagrams import diagram_markdown, reviewed_diagrams
from core.models import ResultVersion, TicketPublicationDraft
from core.ticket_api import router
from core.ticket_publication import preview, publish

pytestmark = pytest.mark.django_db
publication_context = _publication_context


def with_diagrams(version):
    diagrams, _ = reviewed_diagrams([proposal()], reviews(), [claim()])
    return ResultVersion.objects.create(
        request=version.request, number=2, ticket=version.ticket,
        environment_name=version.environment_name, language=version.language,
        evidence={"diagrams": [row.model_dump() for row in diagrams]},
    )


def test_diagrams_stay_out_of_ticket_until_explicit_file_consent(publication_context):
    old, connector, provider, payload = publication_context
    version = with_diagrams(old)
    short = preview(version, connector, "42", presentation=options())
    assert "mermaid" not in short["body"] and short["selected_attachments"] == []
    assert any(row["id"] == "diagrams" for row in short["available_attachments"])
    selected = options(include_attachments=True, include_diagrams=True)
    shown = preview(version, connector, "42", presentation=selected)
    assert shown["selected_attachments"][0]["name"] == "diagrams.md"
    assert "mermaid" not in shown["body"]
    provider.attach.return_value = {"id": "diagram-file"}
    submitted = {**payload, **selected}
    record = publish(version, connector, submitted)
    assert record.status == "PUBLISHED" and record.attachment_delivery[0]["status"] == "TRANSFERRED"
    assert provider.attach.call_args.args[3] == diagram_markdown(version.evidence["diagrams"]).encode()
    assert publish(version, connector, submitted).pk == record.pk
    provider.create.assert_called_once()
    provider.attach.assert_called_once()


@pytest.mark.parametrize("selection", [
    {"include_diagrams": True},
    {"ticket_format": "project", "include_attachments": True, "include_diagrams": True},
])
def test_annex_requires_attachment_consent_and_an_unrestricted_format(publication_context, selection):
    old, connector, provider, _ = publication_context
    version = with_diagrams(old)
    if selection.get("ticket_format") == "project":
        provider.options.return_value["templates"] = [{"id": "feature", "name": "Feature"}]
        selection = {**selection, "template_id": "feature"}
    with pytest.raises(HttpError) as error:
        preview(version, connector, "42", presentation=options(**selection))
    assert error.value.status_code == 422
    provider.create.assert_not_called()
    provider.attach.assert_not_called()


def test_unsupported_destination_cannot_transfer_an_annex(publication_context):
    old, connector, provider, _ = publication_context
    connector.platform = "github"
    version = with_diagrams(old)
    shown = preview(version, connector, "42", presentation=options())
    assert not next(row for row in shown["available_attachments"] if row["id"] == "diagrams")["transferable"]
    with pytest.raises(HttpError):
        preview(version, connector, "42", presentation=options(include_attachments=True, include_diagrams=True))
    provider.create.assert_not_called()


def test_pre_annex_saved_edits_and_publication_digest_remain_recoverable(publication_context):
    version, connector, provider, payload = publication_context
    selected = options()
    shown = preview(version, connector, "42", presentation=selected)
    draft = TicketPublicationDraft.objects.get(pk=shown["draft_id"])
    historical = {key: value for key, value in draft.presentation.items() if key != "include_diagrams"}
    draft.presentation = historical
    draft.content = {**draft.content, "title": "Saved human title", "body": "Saved human description"}
    draft.save()
    revision = draft.revision
    restored = preview(version, connector, "42", presentation=selected, restore=True)
    assert restored["title"] == "Saved human title" and restored["body"] == "Saved human description"
    assert restored["draft_revision"] == revision
    record = publish(version, connector, {**payload, **selected})
    assert "include_diagrams" not in record.snapshot
    result = TestClient(router).post(f"/requests/{version.request_id}/versions/1/publications", json={
        **payload, **selected, "idempotency_key": str(payload["idempotency_key"]),
    })
    assert result.status_code == 200 and result.json()["id"] == str(record.pk)
    provider.create.assert_called_once()


def test_unselected_annex_does_not_change_publication_identity(publication_context):
    version, connector, provider, payload = publication_context
    first = publish(version, connector, {**payload, **options()})
    again = publish(version, connector, {**payload, **options(), "include_diagrams": False,
                                        "idempotency_key": uuid.uuid4()})
    assert first.pk == again.pk
    provider.create.assert_called_once()
