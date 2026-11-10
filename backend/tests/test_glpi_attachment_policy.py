"""Native format restrictions and actual storage confirmation precede success."""

import hashlib

import pytest
from ninja.errors import HttpError
from test_ticket_providers import connector, glpi_routes
from test_ticket_providers import transport as transport
from test_ticket_publication import publication_context as publication_context
from test_v25_tickets import attachment, options

from core.ticket_providers import NetworkUncertain, provider_for
from core.ticket_publication import preview, publish


def test_glpi_native_upload_formats_exclude_disabled_and_invalid_entries(transport):
    routes = glpi_routes()
    routes[("GET", "/apirest.php/DocumentType")] = (200, [
        {"ext": "XLSX", "is_uploadable": 1},
        {"ext": "txt", "is_uploadable": True},
        {"ext": "sql", "is_uploadable": 0},
        {"ext": "md", "is_uploadable": "0"},
        {"ext": "*", "is_uploadable": 1},
        {"ext": "../exe", "is_uploadable": 1},
    ])
    calls = transport(routes)
    policy = provider_for(connector("glpi")).attachment_policy("0")
    assert policy == {"enabled": True, "max_bytes": 25 * 1024 * 1024, "extensions": ["txt", "xlsx"]}
    assert len(calls) == 2 and all(call.method == "GET" for call in calls)


@pytest.mark.parametrize("status", [403, 404])
def test_glpi_unreadable_format_catalogue_fails_closed(transport, status):
    routes = glpi_routes()
    routes[("GET", "/apirest.php/DocumentType")] = (status, {})
    transport(routes)
    assert not provider_for(connector("glpi")).attachment_policy("0")["enabled"]


@pytest.mark.parametrize("stored,confirmed", [
    ({"filename": "proof.txt", "filepath": "TXT/proof.txt", "sha1sum": hashlib.sha1(b"proof").hexdigest()}, True),
    ({"filename": None, "filepath": None, "sha1sum": None}, False),
    ({"filename": "proof.txt", "filepath": None}, False),
    ({"filename": "proof.txt", "filepath": "TXT/proof.txt", "sha1sum": "0" * 40}, False),
])
def test_glpi_only_links_a_document_after_storage_confirmation(transport, stored, confirmed):
    routes = glpi_routes()
    routes.update({
        ("POST", "/apirest.php/Document"): (201, {"id": 7}),
        ("GET", "/apirest.php/Document/7"): (200, stored),
        ("POST", "/apirest.php/Document_Item"): (201, {"id": 11}),
    })
    calls = transport(routes)
    provider = provider_for(connector("glpi"))
    provider.start()
    if confirmed:
        assert provider.attach("0", "6", {"name": "proof.txt", "mime": "text/plain"}, b"proof") == {"id": "7"}
    else:
        with pytest.raises(NetworkUncertain, match="could not be confirmed"):
            provider.attach("0", "6", {"name": "proof.txt", "mime": "text/plain"}, b"proof")
    assert sum(call.url.path.endswith("/Document_Item") for call in calls) == int(confirmed)
    assert sum(call.method == "POST" and call.url.path.endswith("/Document") for call in calls) == 1


@pytest.mark.django_db
def test_unsupported_selected_format_is_visible_and_blocks_creation(publication_context, settings, monkeypatch):
    version, connection, provider, payload = publication_context
    original = attachment(version, settings)
    provider.attachment_policy.return_value = {"enabled": True, "max_bytes": 25000000, "extensions": ["xlsx"]}
    monkeypatch.setattr("core.ticket_providers.provider_for", lambda connection: provider)
    shown = preview(version, connection, "42", presentation=options())
    row = next(item for item in shown["available_attachments"] if item["id"] == str(original.pk))
    assert not row["transferable"] and row["reason"] == "This destination does not allow this file format."
    with pytest.raises(HttpError, match="cannot be transferred"):
        publish(version, connection, {**payload, **options(include_attachments=True, attachment_ids=[str(original.pk)])})
    provider.create.assert_not_called()
    provider.attach.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("lost_response", [False, True])
def test_existing_operation_survives_a_changed_upload_policy(publication_context, settings, monkeypatch, lost_response):
    version, connection, provider, payload = publication_context
    original = attachment(version, settings)
    provider.attachment_policy.return_value = {"enabled": True, "max_bytes": 25000000, "extensions": ["txt"]}
    provider.attach.return_value = {"id": "file-7"}
    monkeypatch.setattr("core.ticket_providers.provider_for", lambda connection: provider)
    if lost_response:
        provider.create.side_effect = NetworkUncertain("Lost response after acceptance")
    submitted = {**payload, **options(include_attachments=True, attachment_ids=[str(original.pk)])}
    first = publish(version, connection, submitted)
    assert first.status == ("UNCERTAIN" if lost_response else "PUBLISHED")
    provider.attachment_policy.return_value = {"enabled": False, "max_bytes": 0, "extensions": []}
    provider.find.return_value = {"external_id": "123", "external_key": "#1", "url": "https://gitlab.example/team/project/-/issues/1"}
    again = publish(version, connection, submitted)
    assert again.pk == first.pk and again.status == "PUBLISHED"
    provider.create.assert_called_once()
    assert provider.attach.call_count == (0 if lost_response else 1)
    assert again.attachment_delivery[0]["status"] == ("UNCERTAIN" if lost_response else "TRANSFERRED")
    with pytest.raises(HttpError, match="different content|already has a publication"):
        publish(version, connection, {**submitted, "attachment_ids": []})
    provider.create.assert_called_once()
    assert provider.attach.call_count == (0 if lost_response else 1)
