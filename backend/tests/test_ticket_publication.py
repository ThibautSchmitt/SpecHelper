"""Publication contracts: confirmation, least privilege, snapshots and safe retries."""

import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.db import IntegrityError
from django.utils import timezone
from ninja.errors import HttpError
from ninja.testing import TestClient

from core.models import GeneratedArtifact, PublishedTicket, Request, ResultVersion, TicketConnector
from core.secrets import decrypt, encrypt
from core.ticket_api import router
from core.ticket_providers import NetworkUncertain, TicketProviderError
from core.ticket_publication import preview, publish, safe_provider_error, validate_base_url

pytestmark = pytest.mark.django_db


@pytest.fixture
def publication_context(environment, storage, monkeypatch):
    request = Request.objects.create(environment=environment, need="Export active contracts")
    version = ResultVersion.objects.create(
        request=request,
        number=1,
        environment_name=environment.name,
        ticket={
            "title": "Export contracts",
            "context": "Audit preparation",
            "need": "Share active contracts",
        },
    )
    GeneratedArtifact.objects.create(
        version=version, name="ticket.md", content="# Export contracts\n\nAudit preparation"
    )
    connector = TicketConnector.objects.create(
        name="Team GitLab",
        platform="gitlab",
        base_url="https://gitlab.example",
        secret=encrypt("fixture-secret"),
        projects=["42"],
        default_project="42",
        status="CONNECTED",
    )
    provider = Mock()
    provider.projects.return_value = [{"id": "42", "name": "Team"}, {"id": "99", "name": "Other"}]
    provider.options.return_value = {
        "revision": "revision-one",
        "fields": [],
        "labels": [{"id": "bug", "name": "Bug"}],
        "assignees": [{"id": "10", "name": "A user"}],
        "templates": [],
        "issue_types": [],
        "template_body": "",
        "format": "markdown",
    }
    provider.create.return_value = {
        "external_id": "123",
        "external_key": "#1",
        "url": "https://gitlab.example/team/project/-/issues/1",
    }
    provider.find.return_value = None
    monkeypatch.setattr("core.ticket_publication.provider_for", lambda connector: provider)
    monkeypatch.setattr("core.ticket_api.provider_for", lambda connector: provider)
    payload = {
        "connector_id": connector.pk,
        "project": "42",
        "title": "Human-edited title",
        "body": "Human-reviewed description",
        "fields": {},
        "labels": ["bug"],
        "assignees": ["10"],
        "template_id": "",
        "issue_type": "",
        "options_revision": "revision-one",
        "idempotency_key": uuid.uuid4(),
        "confirmed": True,
    }
    return version, connector, provider, payload


def test_confirmed_publication_preserves_exact_version_and_edited_payload(publication_context):
    version, connector, provider, payload = publication_context
    record = publish(version, connector, payload)
    assert record.status == "PUBLISHED"
    assert record.version_id == version.pk
    assert record.request_id == version.request_id
    assert record.title == "Human-edited title"
    assert record.body == "Human-reviewed description"
    assert record.snapshot["labels"] == ["bug"]
    assert record.external_reference.startswith("spechelper:")
    provider.create.assert_called_once_with("42", record.snapshot, record.external_reference)
    version.refresh_from_db()
    assert version.ticket["title"] == "Export contracts"
    assert version.artifacts.get(name="ticket.md").content.startswith("# Export contracts")
    with pytest.raises(ValueError, match="immutable"):
        record.save()


def test_same_and_different_keys_cannot_duplicate_logical_publication(publication_context):
    version, connector, provider, payload = publication_context
    first = publish(version, connector, payload)
    assert publish(version, connector, payload).pk == first.pk
    assert publish(version, connector, {**payload, "idempotency_key": uuid.uuid4()}).pk == first.pk
    assert provider.create.call_count == 1
    assert PublishedTicket.objects.count() == 1
    with pytest.raises(HttpError, match="different content"):
        publish(version, connector, {**payload, "body": "Changed"})


def test_concurrent_click_observes_persisted_claim_before_remote_write(publication_context):
    version, connector, provider, payload = publication_context
    observed = []
    result = provider.create.return_value

    def concurrent_click(*args):
        observed.append(publish(version, connector, {**payload, "idempotency_key": uuid.uuid4()}))
        return result

    provider.create.side_effect = concurrent_click
    record = publish(version, connector, payload)
    assert observed[0].pk == record.pk
    assert observed[0].status == "PUBLISHING"
    assert provider.create.call_count == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("confirmed", False),
        ("project", "99"),
        ("fields", {"forbidden": "x"}),
        ("labels", ["unknown"]),
        ("assignees", ["unknown"]),
    ],
)
def test_rejected_payloads_never_write(publication_context, field, value):
    version, connector, provider, payload = publication_context
    with pytest.raises(HttpError):
        publish(version, connector, {**payload, field: value})
    provider.create.assert_not_called()
    assert not PublishedTicket.objects.exists()


def test_revoked_live_project_access_never_writes(publication_context):
    version, connector, provider, payload = publication_context
    provider.projects.return_value = []
    with pytest.raises(HttpError) as exc:
        publish(version, connector, payload)
    assert exc.value.status_code == 403
    provider.create.assert_not_called()


def test_changed_options_require_new_preview(publication_context):
    version, connector, provider, payload = publication_context
    provider.options.return_value["revision"] = "changed-template"
    with pytest.raises(HttpError, match="changed") as exc:
        publish(version, connector, payload)
    assert exc.value.status_code == 409
    provider.create.assert_not_called()


def test_required_field_is_not_invented_and_template_mapping_is_deterministic(publication_context):
    version, connector, provider, payload = publication_context
    options = provider.options.return_value
    options["template_body"] = (
        "## Context\n\nReplace me\n\n## Special business field\n\nHuman input required\n"
    )
    options["fields"] = [
        {"id": "context", "label": "Context", "type": "textarea", "required": False},
        {"id": "business", "label": "Cost center", "type": "text", "required": True},
    ]
    result = preview(version, connector, "42")
    assert result["values"] == {"context": "Audit preparation", "business": ""}
    assert "## Context\n\nAudit preparation" in result["body"]
    assert "## Special business field\n\nHuman input required" in result["body"]
    with pytest.raises(HttpError, match="required"):
        publish(version, connector, payload)
    provider.create.assert_not_called()
    record = publish(version, connector, {**payload, "fields": {"business": "FIN"}})
    assert record.status == "PUBLISHED"


def test_form_only_template_maps_fields_without_duplicating_generic_ticket(publication_context):
    version, connector, provider, payload = publication_context
    provider.options.return_value.update(
        render_fields=True,
        fields=[
            {
                "id": "context",
                "label": "Context",
                "type": "textarea",
                "required": True,
                "default": "",
            },
        ],
    )
    result = preview(version, connector, "42")
    assert result["body"] == ""
    assert result["values"]["context"] == "Audit preparation"
    record = publish(version, connector, {**payload, "body": "", "fields": result["values"]})
    assert record.status == "PUBLISHED"


def test_template_defaults_and_fixed_values_are_respected(publication_context):
    version, connector, provider, payload = publication_context
    provider.options.return_value.update(
        defaults={"title": "Template prefix"},
        fields=[
            {
                "id": "fixed",
                "label": "Context",
                "type": "text",
                "required": True,
                "default": "Approved",
                "read_only": True,
            },
        ],
    )
    result = preview(version, connector, "42")
    assert result["title"] == "Template prefix"
    assert result["values"]["fixed"] == "Approved"
    with pytest.raises(HttpError, match="fixed"):
        publish(version, connector, {**payload, "fields": {"fixed": "Changed"}})
    provider.create.assert_not_called()


def test_network_uncertainty_reconciles_without_creating_again(publication_context):
    version, connector, provider, payload = publication_context
    provider.create.side_effect = NetworkUncertain(
        "Remote timeout fixture-secret https://private.example"
    )
    first = publish(version, connector, payload)
    assert first.status == "UNCERTAIN"
    assert "fixture-secret" not in first.error
    assert publish(version, connector, payload).status == "UNCERTAIN"
    assert provider.create.call_count == 1
    provider.find.return_value = {
        "external_id": "123",
        "external_key": "#1",
        "url": "https://gitlab.example/project/issues/1",
    }
    # A template update does not prevent reconciliation of an accepted write.
    provider.options.return_value["revision"] = "changed"
    recovered = publish(version, connector, payload)
    assert recovered.status == "PUBLISHED"
    assert recovered.pk == first.pk
    assert provider.create.call_count == 1


def test_crashed_claim_recovers_by_search_only(publication_context):
    version, connector, provider, payload = publication_context
    provider.create.side_effect = RuntimeError("fixture-secret")
    record = publish(version, connector, payload)
    PublishedTicket.objects.filter(pk=record.pk).update(
        status="PUBLISHING", updated_at=timezone.now() - timedelta(minutes=5)
    )
    record = publish(version, connector, payload)
    assert record.status == "UNCERTAIN"
    provider.find.assert_called_once_with("42", record.external_reference)
    assert provider.create.call_count == 1


def test_failed_reconciliation_never_becomes_a_retryable_write(publication_context):
    version, connector, provider, payload = publication_context
    provider.create.side_effect = NetworkUncertain("Write timed out")
    assert publish(version, connector, payload).status == "UNCERTAIN"
    provider.find.side_effect = TicketProviderError("Read authorization expired")
    assert publish(version, connector, payload).status == "UNCERTAIN"
    provider.find.side_effect = None
    provider.find.return_value = None
    assert publish(version, connector, payload).status == "UNCERTAIN"
    assert provider.create.call_count == 1


def test_definitive_rejection_is_safe_and_retryable(publication_context):
    version, connector, provider, payload = publication_context
    provider.create.side_effect = TicketProviderError("Authorization header fixture-secret")
    record = publish(version, connector, payload)
    assert record.status == "ERROR"
    assert "fixture-secret" not in record.error
    provider.create.side_effect = None
    assert publish(version, connector, payload).status == "PUBLISHED"
    assert PublishedTicket.objects.count() == 1


def test_corrected_payload_after_rejection_preserves_history_without_old_key_repost(
    publication_context,
):
    version, connector, provider, payload = publication_context
    provider.create.side_effect = TicketProviderError("The title was rejected")
    rejected = publish(version, connector, payload)
    provider.create.side_effect = None
    corrected_payload = {**payload, "title": "Corrected title", "idempotency_key": uuid.uuid4()}
    corrected = publish(version, connector, corrected_payload)
    assert corrected.status == "PUBLISHED"
    assert corrected.pk != rejected.pk
    rejected.refresh_from_db()
    assert rejected.status == "ERROR"
    assert rejected.title == "Human-edited title"
    with pytest.raises(HttpError) as exc:
        publish(version, connector, payload)
    assert exc.value.status_code == 409
    assert provider.create.call_count == 2
    assert PublishedTicket.objects.count() == 2


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://evil.example/1",
        "https://user:secret@gitlab.example/1",
        "http://gitlab.example/1",
    ],
)
def test_unsafe_external_url_is_never_published(publication_context, url):
    version, connector, provider, payload = publication_context
    provider.create.return_value["url"] = url
    record = publish(version, connector, payload)
    assert record.status == "UNCERTAIN"
    assert record.url == ""


@pytest.mark.parametrize("external_id", [None, True, False, "", " ", " 123", [], {}, 0, -1])
def test_invalid_external_identity_never_becomes_a_success(publication_context, external_id):
    version, connector, provider, payload = publication_context
    provider.create.return_value["external_id"] = external_id
    record = publish(version, connector, payload)
    assert record.status == "UNCERTAIN"
    assert record.external_id == ""


@pytest.mark.parametrize(
    "message",
    [
        "GLPI template contains an unsupported field; use a supported template or the native ticket form",
        "GLPI template hides a field without an accessible default; use the native ticket form",
        "Jira requires a field type not supported by this connector",
        "Unsupported GitHub issue form field",
    ],
)
def test_known_unsupported_templates_offer_actionable_native_form_fallback(message):
    assert "native ticket form" in safe_provider_error(TicketProviderError(message))


def test_safe_error_allowlist_never_reflects_unknown_exception_data():
    assert "create-ticket permissions" in safe_provider_error(
        TicketProviderError("Ticket platform denied authentication or permission")
    )
    assert "Reload and review" in safe_provider_error(
        TicketProviderError("Ticket options changed; review the publication again")
    )
    for error in (
        TicketProviderError("fixture-secret https://private.example"),
        TicketProviderError("Unsupported GitHub issue form field fixture-secret"),
        RuntimeError("Unsupported GitHub issue form field"),
    ):
        message = safe_provider_error(error)
        assert "fixture-secret" not in message
        assert "private.example" not in message
        assert "native ticket form" not in message


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:secret@host",
        "https://host?token=secret",
        "https://host/#fragment",
        "https://host/api/%2e%2e/admin",
        "https://host/api\\admin",
        "https://host:bad/api",
    ],
)
def test_invalid_connector_url_is_rejected(url):
    with pytest.raises(HttpError):
        validate_base_url(url)


def test_self_hosted_http_url_is_explicitly_supported():
    assert (
        validate_base_url("http://glpi.internal:8080/apirest.php/")
        == "http://glpi.internal:8080/apirest.php"
    )


def test_connector_api_encrypts_and_never_returns_secrets(publication_context):
    _, connector, provider, _ = publication_context
    client = TestClient(router)
    response = client.post(
        "/ticket-connectors",
        json={
            "name": "New connector",
            "platform": "jira",
            "base_url": "https://jira.example",
            "secret": "plain-fixture-secret",
            "projects": ["PROJ"],
        },
    )
    assert response.status_code == 200
    assert "plain-fixture-secret" not in response.content.decode()
    created = TicketConnector.objects.get(pk=response.json()["id"])
    assert created.secret != "plain-fixture-secret"
    assert decrypt(created.secret) == "plain-fixture-secret"
    provider.test.side_effect = RuntimeError("plain-fixture-secret")
    response = client.post(f"/ticket-connectors/{created.pk}/test")
    assert response.json()["status"] == "ERROR"
    assert "plain-fixture-secret" not in response.content.decode()
    # Admin discovery can list all accessible projects; preview still enforces allowlisting.
    assert client.get(f"/ticket-connectors/{connector.pk}/projects").json()[1]["id"] == "99"


def test_api_confirmation_version_history_filters_and_unknown_fields(publication_context):
    version, connector, provider, payload = publication_context
    client = TestClient(router)
    endpoint = f"/requests/{version.request_id}/versions/1/publications"
    payload = {**payload, "idempotency_key": str(payload["idempotency_key"])}
    for confirmed in (False, "true", 1):
        assert client.post(endpoint, json={**payload, "confirmed": confirmed}).status_code == 422
    assert client.post(endpoint, json={**payload, "unknown": "field"}).status_code == 422
    assert client.post(endpoint, json=payload).json()["status"] == "PUBLISHED"
    history = client.get(endpoint).json()
    assert history[0]["version_number"] == 1
    assert history[0]["options_revision"] == "revision-one"
    assert client.get("/tickets?platform=jira").json()["total"] == 0
    assert client.get("/tickets").json()["environments"] == ["Staging"]
    assert (
        client.get("/tickets?platform=gitlab&environment=Staging&search=Human").json()["total"] == 1
    )
    assert client.delete(f"/ticket-connectors/{connector.pk}").status_code == 409
    provider.create.assert_called_once()


def test_database_constraints_guard_cross_process_and_external_identity(publication_context):
    version, connector, _, payload = publication_context
    record = publish(version, connector, payload)
    values = {
        field.name: getattr(record, field.name)
        for field in PublishedTicket._meta.fields
        if field.name not in {"id", "created_at", "updated_at"}
    }
    values.update(
        idempotency_key=uuid.uuid4(), external_reference="spechelper:" + str(uuid.uuid4())
    )
    from django.db import transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        PublishedTicket.objects.create(**values)


def test_published_destination_cannot_be_silently_repointed(publication_context):
    version, connector, _, payload = publication_context
    publish(version, connector, payload)
    response = TestClient(router).put(
        f"/ticket-connectors/{connector.pk}",
        json={
            "name": connector.name,
            "platform": connector.platform,
            "base_url": "https://different.example",
            "projects": connector.projects,
        },
    )
    assert response.status_code == 409
    connector.refresh_from_db()
    assert connector.base_url == "https://gitlab.example"


def test_unavailable_template_and_unknown_required_type_fail_before_write(publication_context):
    version, connector, provider, payload = publication_context
    with pytest.raises(HttpError, match="template"):
        publish(version, connector, {**payload, "template_id": "missing"})
    provider.options.return_value["fields"] = [
        {"id": "custom", "label": "Custom", "type": "unsupported", "required": True}
    ]
    with pytest.raises(HttpError, match="unsupported"):
        publish(version, connector, {**payload, "fields": {"custom": "human value"}})
    provider.create.assert_not_called()
