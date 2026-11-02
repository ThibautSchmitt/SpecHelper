"""Creation reuses the existing context validators and frozen, on-demand sources."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core import environment_context
from core.models import ContextResource, Environment, Job, Request

pytestmark = pytest.mark.django_db


@pytest.fixture
def create(client, monkeypatch):
    # Source selection has its own integration tests; no remote Git access here.
    monkeypatch.setattr("core.environments.validate", lambda payload: None)
    def post(**changes):
        return client.post("/api/environments", {"name":"Knowledge fixture",
            "repositories":[{"repository":"fixture/project", "branch":"main"}], **changes},
            content_type="application/json")
    return post


def test_environment_creation_still_accepts_no_optional_knowledge(create):
    response = create()
    assert response.status_code == 201, response.content
    value = Environment.objects.get(pk=response.json()["id"])
    assert value.context_instructions == "" and value.official_references == []
    assert response.json()["knowledge_summary"] == {"has_text":False, "documents":0, "sites":0}
    assert Job.objects.filter(kind="sync", target=str(value.pk)).count() == 1


def test_creation_preserves_context_and_general_public_reference_notes(create):
    response = create(context_instructions="An ancillary benefit is a complementary payment.",
        official_references=[{"url":"community.example.org/guide", "note":"User-provided reference; check its applicability."}])
    assert response.status_code == 201, response.content
    value = Environment.objects.get(pk=response.json()["id"])
    assert value.context_instructions == "An ancillary benefit is a complementary payment."
    assert value.official_references == [{"url":"https://community.example.org/guide", "note":"User-provided reference; check its applicability."}]
    assert value.instructions_enabled is True
    assert response.json()["knowledge_summary"] == {"has_text":True, "documents":0, "sites":1}
    request = Request.objects.create(environment=value, need="Explain this term", analysis_protocol="2.4")
    frozen = environment_context.freeze_context(request)
    assert frozen["instructions"]["mode"] == "factual"
    assert frozen["instructions"]["text"] == value.context_instructions
    assert "verified" not in frozen["official_references"][0]


@pytest.mark.parametrize("changes", [
    {"context_instructions":"x" * 4001},
    {"context_instructions":"invalid\x00value"},
    {"official_references":[{"url":"https://127.0.0.1/private", "note":""}]},
    {"official_references":[{"url":"https://docs.example.org", "note":"x" * 1001}]},
    {"official_references":[{"url":"https://docs.example.org", "note":""}] * 13},
])
def test_invalid_creation_knowledge_cannot_leave_a_partial_environment(create, changes):
    before = Job.objects.count()
    assert create(**changes).status_code == 422
    assert not Environment.objects.filter(name="Knowledge fixture").exists()
    assert Job.objects.count() == before


def test_creation_rejects_configured_secrets_in_text_and_reference_notes(create, monkeypatch):
    monkeypatch.setattr("core.sensitive_data.configured_secrets", lambda:["fixture-knowledge-secret"])
    for values in ({"context_instructions":"Use fixture-knowledge-secret"},
                   {"official_references":[{"url":"https://docs.example.org", "note":"fixture-knowledge-secret"}]}):
        response = create(**values)
        assert response.status_code == 422 and "fixture-knowledge-secret" not in response.content.decode()
        assert not Environment.objects.filter(name="Knowledge fixture").exists()


def test_collapsed_summary_does_not_load_document_contents(client, create, storage, monkeypatch):
    value = Environment.objects.get(pk=create().json()["id"])
    result = environment_context.upload_resource(value.pk, SimpleUploadedFile("policy.md", b"Keep this exact reference.", "text/plain"), value.context_revision)
    resource = ContextResource.objects.get(environment=value)
    environment_context.edit_resource(value.pk, resource.pk, result["revision"], enabled=False)
    monkeypatch.setattr("core.environment_context.checked_path", lambda version: pytest.fail("Collapsed summaries must not read document contents"))
    row = next(row for row in client.get("/api/environments").json() if row["id"] == value.pk)
    assert row["knowledge_summary"]["documents"] == 1
