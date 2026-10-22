"""Creation freezes instance orchestration policy and validated business categories."""

import pytest
from django.test import Client

from core.analysis_flow import context
from core.environment_context import freeze_context
from core.models import AIConnection, InstanceSettings, Request, ResultVersion

pytestmark = pytest.mark.django_db


def create(client, environment, path, **payload):
    return client.post(
        path,
        {
            "environment_id": environment.id,
            "need": "Explain the active export behavior.",
            **payload,
        },
        content_type="application/json",
    )


@pytest.mark.parametrize("path", ["/api/requests", "/api/questions"])
@pytest.mark.parametrize("legacy", [True, False])
def test_form_payload_cannot_override_instance_comparison(environment, path, legacy):
    client = Client()
    for allowed in (True, False):
        InstanceSettings.objects.update_or_create(pk=1, defaults={"allow_confrontation": allowed})
        response = create(client, environment, path, confrontation=legacy)
        assert response.status_code == 201, response.content
        assert response.json()["confrontation"] is allowed
        assert Request.objects.get(pk=response.json()["id"]).confrontation is allowed


@pytest.mark.parametrize("reason", ["disabled", "no_role", "disconnected", "identity"])
def test_comparison_requires_authenticated_enabled_counter_role(environment, reason):
    from core.providers import identity_for

    connection = AIConnection.objects.get(pk=1)
    identity = identity_for(connection)
    if reason == "disabled":
        connection.enabled = False
    elif reason == "no_role":
        connection.roles = ["analyst", "verifier"]
    elif reason == "disconnected":
        connection.status = "DISCONNECTED"
    else:
        identity.status = "DISCONNECTED"
        identity.credential_id = identity.id
        identity.save()
    connection.save()
    result = create(Client(), environment, "/api/requests", confrontation=True)
    assert result.status_code == 201
    assert result.json()["confrontation"] is False


@pytest.mark.parametrize("availability", ["BUSY", "QUOTA_EXHAUSTED", "MODEL_UNAVAILABLE"])
def test_transient_capacity_does_not_change_single_account_policy(environment, availability):
    AIConnection.objects.filter(pk=1).update(availability=availability)
    result = create(Client(), environment, "/api/questions")
    assert result.status_code == 201
    assert result.json()["confrontation"] is True


@pytest.mark.parametrize(
    "path,category", [("/api/requests", "bug"), ("/api/questions", "architecture")]
)
def test_category_reaches_analysis_and_frozen_run_context(environment, category, path):
    client = Client()
    response = create(client, environment, path, category=category)
    assert response.status_code == 201
    value = Request.objects.get(pk=response.json()["id"])
    assert response.json()["category"] == category
    assert context(value)["category"] == category
    assert client.get(f"{path}/{value.id}").json()["category"] == category
    launched = client.post(f"{path}/{value.id}/analyze", {}, content_type="application/json")
    assert launched.status_code == 200, launched.content
    run = value.analysis_runs.get()
    assert run.context_snapshot["dossier"]["category"] == category
    original = run.context_snapshot
    value.category = "feature" if path.endswith("requests") else "functional"
    value.save()
    freeze_context(value)
    run.refresh_from_db()
    assert run.context_snapshot == original


@pytest.mark.parametrize(
    "path,category", [("/api/requests", "architecture"), ("/api/questions", "feature")]
)
def test_cross_intent_categories_rejected(environment, path, category):
    assert create(Client(), environment, path, category=category).status_code == 422
    assert not Request.objects.exists()


def test_derived_request_uses_current_policy_and_own_category(environment, storage):
    question = Request.objects.create(workflow="question", environment=environment, need="Why?")
    version = ResultVersion.objects.create(
        request=question,
        number=1,
        status="READY",
        explanation={"title": "Answer", "summary": "A fact"},
    )
    client = Client()
    for allowed in (False, True):
        InstanceSettings.objects.update_or_create(pk=1, defaults={"allow_confrontation": allowed})
        response = create(
            client,
            environment,
            f"/api/questions/{question.id}/requests",
            source_version=version.number,
            include_context=False,
            confrontation=not allowed,
            category="documentation",
        )
        assert response.status_code == 201, response.content
        assert response.json()["confrontation"] is allowed
        assert response.json()["category"] == "documentation"
    question.refresh_from_db()
    assert question.confrontation is False


def test_existing_models_keep_frozen_comparison_when_settings_change(environment):
    value = Request.objects.create(
        environment=environment, need="Historical request", confrontation=True
    )
    InstanceSettings.objects.update_or_create(pk=1, defaults={"allow_confrontation": False})
    response = Client().get(f"/api/requests/{value.id}")
    assert response.json()["confrontation"] is True
