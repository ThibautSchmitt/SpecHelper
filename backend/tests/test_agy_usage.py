"""Built-in quota metadata is non-generative and never merges independent pools."""

import copy
import json
from types import SimpleNamespace

import pytest
from ninja.errors import HttpError

from core.models import InstanceSettings
from core.orchestration_settings import get_config
from core.providers import candidates, mark_failure, observe, public, record_quota
from runtime import antigravity
from tests.test_antigravity_quota_pools import connections


def envelope():
    return {"status": "SUCCESS", "num_turns": 0,
            "usage": dict.fromkeys(antigravity.USAGE_FIELDS, 0),
            "command": {"name": "usage", "data": {"groups": [
                {"name": "Gemini Models", "buckets": [{"id": "gemini-weekly", "window": "weekly", "remaining_fraction": 0, "reset_time": "2026-11-01T08:15:41Z"}]},
                {"name": "Claude and GPT models", "buckets": [{"id": "3p-weekly", "window": "weekly", "remaining_fraction": 0.25, "reset_time": "2026-11-02T11:26:51Z"}]},
            ]}}}


def read(monkeypatch, value):
    def execute(command, **kwargs):
        assert command == ["agy", "-p", "/usage", "--output-format", "json"]
        assert kwargs["cwd"] == "/isolated"
        return SimpleNamespace(returncode=0, stdout=json.dumps(value).encode())
    monkeypatch.setattr(antigravity.subprocess, "run", execute)
    return antigravity.read_quota({"HOME": "/isolated"})


def test_native_usage_preserves_fractions_scopes_and_exact_resets(monkeypatch):
    result = read(monkeypatch, envelope())
    assert result["gemini-weekly"]["remaining_percent"] == 0
    assert result["3p-weekly"]["remaining_percent"] == 25
    assert result["3p-weekly"]["scope"] == "model_pool"
    assert result["3p-weekly"]["model_pool"] == "claude_gpt"
    assert result["gemini-weekly"]["resets_at"] == "2026-11-01T08:15:41+00:00"


@pytest.mark.parametrize("invalid", ["turn", "tokens", "command", "fraction", "reset"])
def test_invalid_or_consuming_usage_never_becomes_a_quota_observation(monkeypatch, invalid):
    value = copy.deepcopy(envelope())
    if invalid == "turn":
        value["num_turns"] = 1
    elif invalid == "tokens":
        value["usage"]["input_tokens"] = 10
    elif invalid == "command":
        value["command"]["name"] = "prompt"
    elif invalid == "fraction":
        value["command"]["data"]["groups"][0]["buckets"][0]["remaining_fraction"] = 2
    else:
        value["command"]["data"]["groups"][0]["buckets"][0]["reset_time"] = "2026-11-01T08:15:41"
    with pytest.raises(ValueError):
        read(monkeypatch, value)


@pytest.mark.django_db
def test_native_group_observations_recover_only_the_matching_pool(monkeypatch):
    rows = connections()
    mark_failure(rows[0].pk, "QUOTA_EXHAUSTED")
    mark_failure(rows[2].pk, "QUOTA_EXHAUSTED")
    record_quota(rows[0], read(monkeypatch, envelope()))
    available = {row.pk for row in candidates()}
    assert all(row.pk not in available for row in rows[:2])
    assert all(row.pk in available for row in rows[2:])
    assert public(rows[2])["quota_windows"]["3p-weekly"]["remaining_percent"] == 25
    assert public(rows[0])["availability"] == "QUOTA_EXHAUSTED"
    observe(rows[0], {"status": "CONNECTED", "ordinary_usage_allowed": True,
                      "quota_status": {"state": "available"}})
    assert rows[0].pk not in {row.pk for row in candidates()}


@pytest.mark.django_db
def test_instruction_rejection_keeps_administration_usable_without_weakening_execution(client, monkeypatch):
    stored = "Keep shared instructions. password=ee"
    row, _ = InstanceSettings.objects.update_or_create(pk=1, defaults={"orchestration": {"global_instructions": stored}})
    monkeypatch.setattr("core.sensitive_data.configured_secrets", lambda: ["ee"])
    with pytest.raises(HttpError):
        get_config()
    response = client.get("/api/orchestration-settings")
    assert response.status_code == 200
    assert response.json()["reliability_protocol"] == "2.4"
    assert response.json()["global_instructions_requires_review"] is True
    assert response.json()["global_instructions"] == ""
    row.refresh_from_db()
    assert row.orchestration["global_instructions"] == stored
