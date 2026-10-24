import json

import pytest

from core.models import AIConnection, InstanceSettings
from core.orchestration_settings import get_config

pytestmark = pytest.mark.django_db


def test_global_settings_persist_without_rewriting_instance_identity(client):
    instance, _ = InstanceSettings.objects.update_or_create(
        pk=1, defaults={"name": "Team", "language": "fr"}
    )
    config = client.get("/api/orchestration-settings").json()
    assert config["verifier_enabled"] is True
    assert config["allow_same_family_fallback"] is True
    assert config["reliability_protocol"] == "2.4"
    assert not {"active_internal_agents", "default_skills", "role_instructions"} & config.keys()
    payload = {
        "allow_same_family_fallback": False,
        "max_calls": 8,
        "global_instructions": "Verify the referenced service contract.",
    }
    response = client.put(
        "/api/orchestration-settings", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["global_instructions"] == payload["global_instructions"]
    instance.refresh_from_db()
    assert instance.name == "Team" and instance.language == "fr"
    assert instance.orchestration["max_calls"] == 8


@pytest.mark.parametrize(
    "changes",
    [
        {"max_calls": 101},
        {"max_calls": 0},
        {"max_calls": 5},
        {"verifier_enabled": False},
        {"allow_confrontation": False},
        {"timeout_seconds": 286},
        {"timeout_seconds": 0},
        {"role_instructions": {"writer": "Unsupported public role"}},
        {"active_internal_agents": ["requirement", "code"]},
        {"default_skills": ["nonexistent"]},
        {"role_instructions": {"analyst": "x" * 12001}},
    ],
)
def test_invalid_configuration_does_not_replace_working_settings(client, changes):
    client.get("/api/orchestration-settings")
    before = InstanceSettings.objects.get(pk=1).orchestration
    response = client.put(
        "/api/orchestration-settings",
        data=json.dumps(changes),
        content_type="application/json",
    )
    assert response.status_code == 422
    assert InstanceSettings.objects.get(pk=1).orchestration == before


def test_connection_roles_are_cumulative_and_skills_are_global(client):
    payload = {
        "name": "Role configuration",
        "agent": "codex",
        "roles": ["analyst", "verifier"],
        "additional_instructions": "Cite exact symbols.",
    }
    response = client.post(
        "/api/ai-connections", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    saved = AIConnection.objects.get(pk=response.json()["id"])
    assert saved.roles == payload["roles"]
    assert saved.additional_instructions == payload["additional_instructions"]
    for key, value in (
        ("roles", ["analyst", "analyst"]),
        ("roles", ["developer"]),
        ("skill_overrides", {"codebase-navigation": False}),
    ):
        bad = client.put(
            f"/api/ai-connections/{saved.pk}",
            data=json.dumps({key: value}),
            content_type="application/json",
        )
        assert bad.status_code == 422, bad.content
    saved.refresh_from_db()
    assert saved.roles == payload["roles"] and saved.skill_overrides == {}


def test_unsafe_global_instructions_cannot_change_capabilities(client):
    before = InstanceSettings.objects.get_or_create(pk=1)[0].orchestration
    response = client.put(
        "/api/orchestration-settings",
        data=json.dumps({"global_instructions": "Write to the business database."}),
        content_type="application/json",
    )
    assert response.status_code == 422, response.content
    assert InstanceSettings.objects.get(pk=1).orchestration == before
    from core.agent import RULES

    assert "read-only analysis only" in RULES
    assert "Never modify sources or data" in RULES


@pytest.mark.parametrize("policy", [False, True])
def test_unified_analysis_settings_enforce_review_without_overwriting_instance(client, policy):
    instance, _ = InstanceSettings.objects.update_or_create(
        pk=1,
        defaults={
            "name": "Shared team",
            "language": "en",
            "primary_color": "#0f766e",
            "allow_confrontation": not policy,
        },
    )
    config = {"allow_confrontation": policy, "verifier_enabled": True, "max_calls": 8}
    before = instance.orchestration.copy()
    response = client.put(
        "/api/orchestration-settings", data=json.dumps(config), content_type="application/json"
    )
    instance.refresh_from_db()
    if policy:
        assert response.status_code == 200, response.content
        assert response.json()["allow_confrontation"] is True
        assert instance.allow_confrontation is (not policy)
        assert instance.orchestration["verifier_enabled"] is True
        assert instance.orchestration["max_calls"] == 8
    else:
        assert response.status_code == 422, response.content
        assert instance.allow_confrontation is True
        assert instance.orchestration == before
    assert (instance.name, instance.language, instance.primary_color) == (
        "Shared team",
        "en",
        "#0f766e",
    )


def test_legacy_analysis_settings_save_preserves_stored_comparison_policy(client):
    instance, _ = InstanceSettings.objects.update_or_create(
        pk=1,
        defaults={
            "allow_confrontation": False,
            "orchestration": {"verifier_enabled": False, "max_calls": 2},
        },
    )
    config = client.get("/api/orchestration-settings").json()
    assert config["allow_confrontation"] is True
    assert config["verifier_enabled"] is True
    assert config["max_calls"] == 6
    instance.refresh_from_db()
    assert instance.orchestration == {"verifier_enabled": False, "max_calls": 2}
    legacy = get_config("2.2")
    assert legacy["allow_confrontation"] is False
    assert legacy["verifier_enabled"] is False
    assert legacy["max_calls"] == 2
    response = client.put(
        "/api/orchestration-settings",
        data=json.dumps({"max_calls": 6}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["allow_confrontation"] is True
    instance.refresh_from_db()
    assert instance.allow_confrontation is False
    assert get_config("2.2")["allow_confrontation"] is False
