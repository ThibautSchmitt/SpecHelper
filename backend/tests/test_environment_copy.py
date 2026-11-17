import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.environment_context import checked_path, edit_resource, upload_resource
from core.models import ContextResource, Environment, Job, Request, TicketConnector

pytestmark = pytest.mark.django_db


def payload(environment, **changes):
    return {"name": "Copied staging", "copy_from_environment_id": environment.pk,
            "expected_source_revision": environment.revision,
            "repositories": [{"repository": "company/backend", "branch": "tag:release/v2"}],
            **changes}


def create(client, data):
    return client.post("/api/environments", data=json.dumps(data), content_type="application/json")


def test_copy_configuration_and_documents_without_history_or_stale_git_state(client, environment, storage):
    from core.models import DatabaseConnection
    from core.secrets import encrypt

    database = DatabaseConnection.objects.create(name="Reader", host="db.example.test", database="business", username="readonly", secret=encrypt("fixture-secret"))
    connector = TicketConnector.objects.create(name="Tracker", platform="gitlab", base_url="https://tracker.example.test")
    connector.environments.add(environment)
    environment.database = database
    environment.context_instructions = "Business rules for test contracts."
    environment.official_references = [{"url": "https://docs.example.test", "title": "Documentation"}]
    environment.library_selection = {"packages": ["shared-knowledge"]}
    environment.save()
    upload_resource(environment.pk, SimpleUploadedFile("rules.md", b"# Current rules"), 1)
    resource = environment.context_resources.get()
    upload_resource(environment.pk, SimpleUploadedFile("rules.md", b"# Updated rules"), 2, resource.pk)
    removed = ContextResource.objects.create(environment=environment, name="Removed", removed=True)
    historical = Request.objects.create(environment=environment, need="Existing conversation", baseline=[{"sha": "a" * 40}])
    response = create(client, payload(environment, database_id=database.pk, publication_connection_ids=[connector.pk]))
    assert response.status_code == 201, response.content
    copied = Environment.objects.get(pk=response.json()["id"])
    assert copied.pk != environment.pk and copied.database_id == database.pk
    assert list(copied.publication_connections.all()) == [connector]
    assert set(connector.environments.values_list("pk", flat=True)) == {environment.pk, copied.pk}
    assert copied.status == "PENDING" and copied.synced_at is None and copied.revision == 1
    repository = copied.repositories.get()
    assert repository.branch == "tag:release/v2" and repository.sha == "" and repository.workspace == ""
    assert repository.git_status == {} and repository.synced_at is None
    assert copied.context_instructions == environment.context_instructions
    assert copied.official_references == environment.official_references
    assert copied.library_selection == environment.library_selection
    document = copied.context_resources.get()
    assert document.pk not in {resource.pk, removed.pk}
    version = document.versions.get()
    assert version.version == 1 and checked_path(version).read_bytes() == b"# Updated rules"
    assert not copied.request_set.exists()
    assert Job.objects.get(kind="sync").target == str(copied.pk)
    assert environment.repositories.get().sha == "a" * 40
    historical.refresh_from_db()
    assert historical.environment_id == environment.pk and historical.baseline == [{"sha": "a" * 40}]
    # Editing/deleting original document identities cannot invalidate the copy.
    edit_resource(environment.pk, resource.pk, 3, remove=True)
    environment.delete()
    document.refresh_from_db()
    assert not document.removed and checked_path(version).read_bytes() == b"# Updated rules"


@pytest.mark.parametrize("changes,status", [
    ({"expected_source_revision": 99}, 409),
    ({"expected_source_revision": None}, 409),
    ({"copy_from_environment_id": 999999}, 404),
    ({"name": "Staging"}, 409),
    ({"repositories": [{"repository": "company/backend", "branch": "bad..ref"}]}, 422),
])
def test_copy_rejects_invalid_or_stale_configuration_without_partial_creation(client, environment, storage, changes, status):
    response = create(client, payload(environment, **changes))
    assert response.status_code == status, response.content
    assert Environment.objects.count() == 1 and not Job.objects.exists()
    assert not ContextResource.objects.exists()
