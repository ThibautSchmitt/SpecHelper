import json

import pytest

from core.models import Environment, EnvironmentRepository, Job, Request

pytestmark = pytest.mark.django_db


def test_edit_environment_preserves_requests_and_unchanged_sources(client, environment):
    historical = Request.objects.create(
        environment=environment,
        need="An already analyzed request",
        status="READY",
        baseline=[{"repository": "company/backend", "branch": "main", "sha": "a" * 40}],
    )
    response = client.patch(
        f"/api/environments/{environment.id}",
        data=json.dumps(
            {
                "name": "Renamed validation environment",
                "repositories": [
                    {"repository": "company/backend", "branch": "main"},
                    {"repository": "company/frontend", "branch": "release/2026"},
                ],
                "database_id": None,
                "expected_revision": 1,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["revision"] == 2
    assert environment.repositories.get(repository="company/backend").sha == "a" * 40
    assert environment.repositories.get(repository="company/frontend").sha == ""
    assert Job.objects.get().payload["changed_repositories"] == ["company/frontend"]
    historical.refresh_from_db()
    assert historical.baseline[0]["sha"] == "a" * 40


def test_stale_edit_and_delete_require_current_explicit_confirmation(client, environment):
    environment.revision = 2
    environment.save()
    payload = {
        "name": "Autre",
        "repositories": [{"repository": "company/backend", "branch": "main"}],
        "expected_revision": 1,
    }
    assert (
        client.patch(
            f"/api/environments/{environment.id}",
            data=json.dumps(payload),
            content_type="application/json",
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/environments/{environment.id}",
            data=json.dumps({"confirm_name": "Autre", "expected_revision": 2}),
            content_type="application/json",
        ).status_code
        == 409
    )
    assert Environment.objects.filter(pk=environment.id).exists()


def test_delete_keeps_history_and_shared_mirrors(client, environment, storage):
    other = Environment.objects.create(name="Another environment", status="READY")
    EnvironmentRepository.objects.create(
        environment=other, repository="company/backend", branch="develop", sha="b" * 40
    )
    historical = Request.objects.create(
        environment=environment,
        environment_name_snapshot=environment.name,
        need="A historical request",
        status="READY",
        baseline=[{"repository": "company/backend", "branch": "main", "sha": "a" * 40}],
    )
    mirror = storage / "git-cache/company/backend.git"
    mirror.mkdir(parents=True)
    (mirror / "evidence").write_text("shared")
    snapshot = storage / "analysis-workspaces" / str(historical.id)
    snapshot.mkdir(parents=True)
    (snapshot / "evidence").write_text("immutable")
    response = client.delete(
        f"/api/environments/{environment.id}",
        data=json.dumps({"confirm_name": environment.name, "expected_revision": 1}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert not Environment.objects.filter(pk=environment.id).exists()
    assert Environment.objects.filter(pk=other.id).exists()
    assert (mirror / "evidence").read_text() == "shared"
    assert (snapshot / "evidence").read_text() == "immutable"
    historical.refresh_from_db()
    assert historical.environment_id is None
    detail = client.get(f"/api/requests/{historical.id}").json()
    assert detail["environment_name"] == environment.name
    assert detail["baseline"][0]["sha"] == "a" * 40
