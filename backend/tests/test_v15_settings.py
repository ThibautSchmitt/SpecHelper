import json

import pytest

from core.models import AIConnection, InstanceSettings

pytestmark = pytest.mark.django_db


def test_role_settings_persist_without_rewriting_instance_identity(client):
    instance, _ = InstanceSettings.objects.update_or_create(
        pk=1, defaults={"name": "Team", "language": "fr"}
    )
    config = client.get("/api/orchestration-settings").json()
    assert config["verifier_enabled"] is True
    assert config["allow_same_family_fallback"] is True
    assert {"requirement", "code", "writer"} <= set(config["active_internal_agents"])
    metadata = {key: config.pop(key) for key in ("available_agents", "available_skills")}
    config.update(
        verifier_enabled=False, allow_same_family_fallback=False, max_calls=8, timeout_seconds=180
    )
    config["role_instructions"]["counter_analyst"] = "Verify the referenced service contract."
    response = client.put(
        "/api/orchestration-settings", data=json.dumps(config), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["role_instructions"] == config["role_instructions"]
    assert response.json()["available_agents"] == metadata["available_agents"]
    instance.refresh_from_db()
    assert instance.name == "Team" and instance.language == "fr"
    assert instance.orchestration["timeout_seconds"] == 180


@pytest.mark.parametrize(
    "changes",
    [
        {"max_calls": 21},
        {"max_calls": 0},
        {"timeout_seconds": 286},
        {"timeout_seconds": 0},
        {"role_instructions": {"writer": "Unsupported public role"}},
        {"active_internal_agents": ["requirement", "code"]},
        {"default_skills": ["nonexistent"]},
        {"role_instructions": {"analyst": "x" * 12001}},
    ],
)
def test_invalid_configuration_does_not_replace_working_settings(client, changes):
    settings = client.get("/api/orchestration-settings").json()
    for key in ("available_agents", "available_skills"):
        settings.pop(key)
    before = InstanceSettings.objects.get(pk=1).orchestration
    response = client.put(
        "/api/orchestration-settings",
        data=json.dumps({**settings, **changes}),
        content_type="application/json",
    )
    assert response.status_code == 422
    assert InstanceSettings.objects.get(pk=1).orchestration == before


def test_connection_roles_are_cumulative_and_skill_overrides_remain_sparse(client):
    settings = client.get("/api/orchestration-settings").json()
    skill = settings["available_skills"][0]["slug"]
    payload = {
        "name": "Role configuration",
        "agent": "codex",
        "roles": ["analyst", "verifier"],
        "additional_instructions": "Cite exact symbols.",
        "skill_overrides": {skill: False},
    }
    response = client.post(
        "/api/ai-connections", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    item = response.json()
    saved = AIConnection.objects.get(pk=item["id"])
    assert saved.roles == payload["roles"]
    assert saved.skill_overrides == {skill: False}
    assert saved.additional_instructions == "Cite exact symbols."
    for key, value in (
        ("roles", ["analyst", "analyst"]),
        ("roles", ["developer"]),
        ("skill_overrides", {"unknown": True}),
    ):
        bad = client.put(
            f"/api/ai-connections/{saved.pk}",
            data=json.dumps({key: value}),
            content_type="application/json",
        )
        assert bad.status_code == 422
    inherited = client.put(
        f"/api/ai-connections/{saved.pk}",
        data=json.dumps({"skill_overrides": {}}),
        content_type="application/json",
    )
    assert inherited.status_code == 200
    saved.refresh_from_db()
    assert saved.skill_overrides == {}


def test_instructions_are_stored_as_data_and_do_not_change_capabilities(client):
    config = client.get("/api/orchestration-settings").json()
    for key in ("available_agents", "available_skills"):
        config.pop(key)
    config["role_instructions"]["analyst"] = "Request write access to the business database."
    assert (
        client.put(
            "/api/orchestration-settings", data=json.dumps(config), content_type="application/json"
        ).status_code
        == 200
    )
    from core.agent import RULES

    assert "read-only analysis only" in RULES
    assert "Never modify sources or data" in RULES
