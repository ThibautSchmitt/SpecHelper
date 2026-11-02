"""Publication contracts: confirmation, least privilege, snapshots and safe retries."""

import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.db import IntegrityError
from django.http import Http404
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
        environment=environment,
        name="Team GitLab",
        platform="gitlab",
        base_url="https://gitlab.example",
        secret=encrypt("fixture-secret"),
        projects=["42"],
        default_project="42",
        status="CONNECTED",
    )
    connector.environments.add(environment)
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
    original_error = record.error
    provider.create.side_effect = None
    retried = publish(version, connector, payload)
    assert retried.status == "PUBLISHED"
    assert retried.attempt_history[0]["status"] == "ERROR"
    assert retried.attempt_history[0]["error"] == original_error
    assert retried.attempt_history[0]["finished_at"]
    assert "fixture-secret" not in str(retried.attempt_history)
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
            "environment_id": connector.environment_id,
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
            "environment_id": connector.environment_id,
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


def test_separate_prepared_tickets_can_publish_to_same_destination(publication_context):
    from core.models import ConversationTicket
    version, connector, provider, payload = publication_context
    first=ConversationTicket.objects.create(request=version.request,source_version=version,draft={"revision":1,"title":"First topic"})
    second=ConversationTicket.objects.create(request=version.request,source_version=version,draft={"revision":1,"title":"Second topic"})
    provider.create.side_effect=[
        {"external_id":"201","external_key":"#201","url":"https://gitlab.example/team/project/-/issues/201"},
        {"external_id":"202","external_key":"#202","url":"https://gitlab.example/team/project/-/issues/202"},
    ]
    deliveries=[]
    for ticket in [first,second]:
        values={**payload,"unverified_confirmed":True,"conversation_ticket_id":str(ticket.pk),"idempotency_key":uuid.uuid4(),"title":ticket.draft["title"]}
        deliveries.append(publish(version,connector,values))
    assert len({d.pk for d in deliveries}) == 2
    assert {d.conversation_ticket_id for d in deliveries} == {first.pk,second.pk}
    assert provider.create.call_count == 2
    assert deliveries[0].snapshot["conversation_ticket_id"] == str(first.pk)
    unrelated=ResultVersion.objects.create(request=version.request,number=2)
    with pytest.raises(Http404):
        preview(unrelated,connector,"42",presentation={"conversation_ticket_id":str(first.pk)})
    assert provider.create.call_count == 2


def test_prepared_standard_preview_uses_its_own_subject_and_preserves_destination_edits(publication_context):
    from core.models import ConversationTicket, TicketPublicationDraft

    version, connector, provider, payload = publication_context
    version.request.language = "en"
    version.request.save()
    ticket = ConversationTicket.objects.create(request=version.request, source_version=version,
        draft={"title":"A narrower correction", "body":"Keep my acceptance criteria.", "source_version":version.number, "revision":1})
    selection={"conversation_ticket_id":str(ticket.pk), "ticket_format":"standard"}
    initial=preview(version,connector,"42",presentation=selection,restore=True)
    assert initial["title"] == "A narrower correction"
    assert "Keep my acceptance criteria." in initial["body"]
    draft=TicketPublicationDraft.objects.get(pk=initial["draft_id"])
    draft.content={**draft.content,"title":"Destination-specific edit","body":"Preserved target content"}
    draft.save()
    restored=preview(version,connector,"42",presentation=selection,restore=True)
    assert restored["title"] == "Destination-specific edit"
    assert restored["body"] == "Preserved target content"
    provider.create.assert_not_called()


def test_discussion_ticket_can_publish_without_an_analysis_only_after_explicit_acknowledgement(publication_context):
    from core.models import ConversationTicket, Job, RequestMessage

    _,connector,provider,_=publication_context
    request=Request.objects.create(environment=connector.environments.first(),need="Reject invalid periods",status="DISCUSSING",language="en")
    anchor=RequestMessage.objects.create(request=request,role="assistant",kind="discussion_reply",content="The period can be checked before saving.")
    ticket=ConversationTicket.objects.create(request=request,draft={"title":"Check periods","body":"Reject invalid periods.","revision":1,"anchor_message_id":anchor.pk})
    client=TestClient(router)
    endpoint=f"/analyses/{request.pk}/tickets/{ticket.pk}"
    response=client.get(endpoint+f"/publication-draft?connector_id={connector.pk}&project=42")
    assert response.status_code == 200,response.content
    draft=response.json()
    assert draft["publication_allowed"] and draft["requires_unverified_confirmation"]
    assert draft["version_id"] is None and not request.versions.exists()
    payload={"conversation_ticket_id":str(ticket.pk),"connector_id":connector.pk,"project":"42",
      "title":draft["title"],"body":draft["body"],"fields":draft["values"],"labels":draft["defaults"]["labels"],"assignees":draft["defaults"]["assignees"],
      "options_revision":draft["options_revision"],"template_id":"","issue_type":"","ticket_format":"standard",
      "draft_id":draft["draft_id"],"draft_revision":draft["draft_revision"],"idempotency_key":str(uuid.uuid4()),"confirmed":True}
    assert client.post(endpoint+"/publications",json=payload).status_code == 409
    provider.create.assert_not_called()
    response=client.post(endpoint+"/publications",json={**payload,"unverified_confirmed":True})
    assert response.status_code == 200,response.content
    assert response.json()["status"] == "PUBLISHED"
    publication=PublishedTicket.objects.get(request=request)
    assert publication.version_id is None and publication.conversation_ticket_id == ticket.pk
    assert publication.snapshot["unverified_confirmed"] is True
    assert client.post(endpoint+"/publications",json={**payload,"unverified_confirmed":True}).json()["id"] == str(publication.pk)
    assert provider.create.call_count == 1
    assert request.messages.filter(kind="ticket_publication").count() == 1
    assert not request.versions.exists() and not Job.objects.filter(kind="analysis",target=str(request.pk)).exists()
    assert client.get("/tickets").json()["items"][0]["request_id"] == str(request.pk)


@pytest.fixture
def discussion_publication(publication_context):
    from core.models import ConversationTicket
    from core.ticket_preparation import publication_source

    _, connector, provider, payload = publication_context
    request = Request.objects.create(environment=connector.environments.first(), need="Check dates", status="DISCUSSING", language="en")
    ticket = ConversationTicket.objects.create(request=request, draft={"title":"Check dates", "body":"Reject invalid periods.", "revision":1})
    source = publication_source(request.pk, ticket_id=ticket.pk)
    return request, ticket, source, connector, provider, {**payload, "conversation_ticket_id":str(ticket.pk), "unverified_confirmed":True}


@pytest.mark.parametrize("uncertain", [False, True])
def test_discussion_publication_failure_never_creates_a_false_success(discussion_publication, uncertain):
    from core.queue import snapshot as activity_snapshot
    request, ticket, source, connector, provider, payload = discussion_publication
    provider.create.side_effect = NetworkUncertain("Lost response fixture-secret") if uncertain else TicketProviderError("Rejected fixture-secret")
    first = publish(source, connector, payload)
    assert first.status == ("UNCERTAIN" if uncertain else "ERROR")
    assert "fixture-secret" not in first.error
    assert not request.messages.filter(kind="ticket_publication").exists()
    assert TestClient(router).get("/tickets").json()["total"] == 0
    assert activity_snapshot()
    ticket.refresh_from_db()
    assert ticket.draft["body"] == "Reject invalid periods."
    if uncertain:
        assert publish(source, connector, payload).status == "UNCERTAIN"
        assert provider.create.call_count == 1
        provider.find.return_value = {"external_id":"123", "external_key":"#1", "url":"https://gitlab.example/team/project/-/issues/1"}
        assert publish(source, connector, payload).status == "PUBLISHED"
        assert publish(source, connector, payload).pk == first.pk
        assert provider.create.call_count == 1
        assert request.messages.filter(kind="ticket_publication").count() == 1


def test_discussion_publication_checks_scope_acknowledgement_and_real_artifacts(discussion_publication):
    from core.models import ConversationTicket
    request, ticket, source, connector, provider, payload = discussion_publication
    client = TestClient(router)
    endpoint = f"/analyses/{request.pk}/tickets/{ticket.pk}"
    assert client.post(endpoint+"/publications", json={**payload,"unverified_confirmed":"true"}).status_code == 422
    foreign = Request.objects.create(need="Another conversation")
    assert client.get(f"/analyses/{foreign.pk}/tickets/{ticket.pk}/publications").status_code == 404
    other = ConversationTicket.objects.create(request=foreign, draft={"title":"Other", "revision":1})
    assert client.get(f"/analyses/{request.pk}/tickets/{other.pk}/publication-draft?connector_id={connector.pk}&project=42").status_code == 404
    for flag in ("include_goal", "include_diagrams", "include_business_analysis", "include_technical_analysis"):
        result = client.post(endpoint+"/publication-preview", json={"connector_id":connector.pk,"project":"42","ticket_format":"standard",flag:True})
        assert result.status_code == 422
    connector.environments.remove(request.environment)
    with pytest.raises(HttpError):
        publish(source, connector, payload)
    provider.create.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_discussion_double_click_uses_one_persisted_claim_on_postgresql(discussion_publication):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, connection

    from core.ticket_preparation import publication_source
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    request, ticket, source, connector, provider, payload = discussion_publication
    entered, release = Event(), Event()
    result = provider.create.return_value
    def slow_provider(*args):
        entered.set()
        assert release.wait(10)
        return result
    def first_click():
        close_old_connections()
        try:
            return publish(publication_source(request.pk, ticket_id=ticket.pk), TicketConnector.objects.get(pk=connector.pk), payload)
        finally:
            close_old_connections()
    provider.create.side_effect = slow_provider
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(first_click)
        try:
            assert entered.wait(10)
            second = publish(source, connector, {**payload,"idempotency_key":uuid.uuid4()})
            assert second.status == "PUBLISHING"
        finally:
            release.set()
        first = future.result(timeout=10)
    assert first.pk == second.pk and first.status == "PUBLISHED"
    assert provider.create.call_count == 1
    assert request.messages.filter(kind="ticket_publication").count() == 1


def test_discussion_ticket_retains_two_destinations_and_links_when_archived(discussion_publication, client):
    request, ticket, source, connector, provider, payload = discussion_publication
    connector.projects = ["42", "99"]
    connector.save(update_fields=["projects"])
    first = publish(source, connector, payload)
    provider.create.return_value = {"external_id":"124", "external_key":"#2", "url":"https://gitlab.example/team/other/-/issues/2"}
    second = publish(source, connector, {**payload,"project":"99","idempotency_key":uuid.uuid4()})
    assert first.pk != second.pk
    assert request.messages.filter(kind="ticket_publication").count() == 2
    request.archived_at = timezone.now()
    request.save(update_fields=["archived_at"])
    detail = client.get(f"/api/analyses/{request.pk}")
    assert detail.status_code == 200
    assert {item["url"] for item in detail.json()["publications"]} == {first.url,second.url}
    assert len(detail.json()["conversation_tickets"]) == 1
    assert TestClient(router).get("/tickets").json()["total"] == 2
    assert not request.versions.exists()
