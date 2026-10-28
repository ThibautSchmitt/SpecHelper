"""Native metadata stays identity scoped and cannot consume an inference turn."""

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from ninja.errors import HttpError

from core.model_catalog import refresh, validate_effort, validate_model
from core.models import AIConnection, AIIdentity
from core.providers import bind_session, normalize_quota_windows, public, quota_exhausted
from core.quota_refresh import record_invocation_metadata
from runtime import model_discovery, server
from runtime.quota import app_server_windows


def test_distinct_windows_credits_and_provider_limits_are_not_collapsed():
    value = app_server_windows({"rateLimits": {
        "limitId": "main", "primary": {"windowDurationMins": 300, "usedPercent": 12},
        "secondary": {"windowDurationMins": 10080, "usedPercent": 81},
        "credits": {"balance": "7.5"},
    }, "rateLimitsByLimitId": {"model-a": {"primary": {"windowDurationMins": 1440, "usedPercent": 100}}}})
    assert value["session"]["remaining_percent"] == 88
    assert value["weekly"]["remaining_percent"] == 19
    assert value["credits"]["remaining_units"] == 7.5
    assert "remaining_percent" not in value["credits"]
    assert app_server_windows({"rateLimits": {"credits": {"balance": "NaN"}}}) == {}
    assert value["limit:model-a:daily"]["scope"] == "provider_limit"
    assert not quota_exhausted(SimpleNamespace(quota_windows=value))
    assert app_server_windows({"rateLimits": None, "rateLimitsByLimitId": []}) == {}
    extra = app_server_windows({"rateLimitsByLimitId": {"only": {"primary": {"windowDurationMins": 2880, "usedPercent": 4}}}})
    assert extra["limit:only:window_2880m"]["remaining_percent"] == 96


def test_unknown_measurements_and_dates_are_never_invented():
    windows = normalize_quota_windows({"daily": {"remaining_percent": 25, "reset_at": "not-a-date"},
                                      "credits": {"remaining_units": 0}, "invalid": {"used_percent": float("nan")}})
    assert windows["daily"]["used_percent"] == 75
    assert "resets_at" not in windows["daily"]
    assert windows["credits"]["remaining_units"] == 0
    assert "remaining_percent" not in windows["credits"]
    assert "invalid" not in windows


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["available", "error", "unavailable"])
def test_invocation_metadata_preserves_shared_busy_leases_and_previous_windows(state):
    identity = AIIdentity.objects.create(agent="codex", credential_id=uuid.uuid4(), availability="BUSY",
                                        quota_windows={"weekly": {"used_percent": 60}})
    connection = AIConnection.objects.create(agent="codex", identity=identity, availability="BUSY")
    other = AIConnection.objects.create(agent="codex", identity=identity)
    isolated = AIIdentity.objects.create(agent="codex", credential_id=uuid.uuid4())
    record_invocation_metadata({"agent": "codex", "identity_id": str(identity.credential_id)}, {
        "quota_status": {"state": state, "private": "discard"},
        "quota_windows": {"session": {"used_percent": 20}} if state == "available" else {},
    })
    identity.refresh_from_db()
    assert identity.availability == "BUSY"
    assert identity.quota_windows["weekly"]["used_percent"] == 60
    if state == "available":
        assert public(other)["quota_windows"]["session"]["remaining_percent"] == 80
    assert public(connection)["quota_status"]["state"] == state
    assert "private" not in json.dumps(identity.quota_windows)
    assert isolated.quota_windows == {}
    record_invocation_metadata({"identity_id": "malformed"}, {"quota_status": {"state": "available"}})


@pytest.mark.django_db
def test_legacy_identity_can_receive_post_invocation_metadata():
    identity = AIIdentity.objects.create(agent="claude", credential_id=None)
    connection = AIConnection.objects.create(agent="claude", identity=identity)
    record_invocation_metadata({"agent": "claude", "identity_id": None}, {"quota_status": {"state": "unavailable"}})
    assert public(connection)["quota_status"]["state"] == "unavailable"


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ["status", "network", "shape"])
def test_transport_failures_mark_observations_stale_without_erasing_them(monkeypatch, settings, failure):
    import httpx

    from core.agent import runtime_call

    settings.RUNTIME_TOKEN = "fixture-only"
    identity = AIIdentity.objects.create(agent="codex", credential_id=uuid.uuid4(), availability="BUSY",
                                        quota_windows={"weekly": {"used_percent": 60}})
    connection = AIConnection.objects.create(agent="codex", identity=identity)
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, *args, **kwargs):
            if failure == "network":
                raise httpx.ReadTimeout("synthetic")
            return SimpleNamespace(status_code=503 if failure == "status" else 200, json=lambda: [])

    monkeypatch.setattr("core.agent.httpx.Client", Client)
    with pytest.raises(ValueError):
        runtime_call("/run", {"agent": "codex", "identity_id": str(identity.credential_id)})
    assert public(connection)["quota_status"]["state"] == "error"
    assert public(connection)["quota_windows"]["weekly"]["used_percent"] == 60
    identity.refresh_from_db()
    assert identity.availability == "BUSY"


@pytest.mark.django_db
def test_model_effort_is_scoped_to_native_identity_capabilities_and_snapshotted(monkeypatch, environment):
    from core.models import Request

    connection = AIConnection.objects.create(agent="codex")
    monkeypatch.setattr("core.model_catalog.runtime_call", lambda *a, **kw: {
        "state": "supported", "reason": "catalog_not_entitlement", "items": [{"identifier": "native", "name": "Native",
        "capabilities": {"reasoning_efforts": ["low", "high", "ultra"], "default_effort": "high", "is_default": True}}]})
    catalog = refresh(connection)
    assert catalog["items"][0]["capabilities"]["reasoning_efforts"] == ["low", "high"]
    validate_effort(connection, "native", "high")
    validate_effort(connection, "", "low")
    with pytest.raises(HttpError):
        validate_effort(connection, "native", "ultra")
    other = AIConnection.objects.create(agent="codex", identity=AIIdentity.objects.create(agent="codex", credential_id=uuid.uuid4()))
    with pytest.raises(HttpError):
        validate_model("codex", "native", other)
    connection.model, connection.reasoning_effort = "native", "high"
    request = Request.objects.create(environment=environment, need="Explain exports")
    first = bind_session(request, connection)
    connection.reasoning_effort = "low"
    second = bind_session(request, connection)
    assert first.pk != second.pk
    assert first.reasoning_effort_snapshot == "high" and second.reasoning_effort_snapshot == "low"


def test_claude_initialize_has_no_user_turn_and_does_not_guess_efforts(monkeypatch, tmp_path):
    def execute(command, **kwargs):
        assert command[:2] == ["claude", "--print"]
        data = json.loads(kwargs["input"])
        assert data["type"] == "control_request" and data["request"]["subtype"] == "initialize"
        assert "prompt" not in data
        return SimpleNamespace(stdout=json.dumps({"type": "control_response", "response": {
            "subtype": "success", "request_id": "spechelper-models", "response": {"models": [
                {"value": "native", "displayName": "Native", "supportsEffort": True, "supportedEffortLevels": ["high", "max", "ultra"]},
                {"value": "legacy", "supportsEffort": False, "supportedEffortLevels": ["high"]},
            ]}}}))
    monkeypatch.setattr(model_discovery.subprocess, "run", execute)
    result = model_discovery.read_claude_models(tmp_path, {})
    assert result[0]["capabilities"]["reasoning_efforts"] == ["high", "max"]
    assert result[1]["capabilities"]["reasoning_efforts"] == []


@pytest.mark.django_db
def test_refresh_preserves_other_models_verified_efforts_and_unregistered_legacy_selection(monkeypatch):
    connection = AIConnection.objects.create(agent="antigravity", model="unregistered-legacy")
    selected = "model-a"
    def metadata(path, **kwargs):
        return {"state": "supported", "reason": "catalog_not_entitlement", "items": [
            {"identifier": name, "name": name, **({"capabilities": {"reasoning_efforts": ["low", "high"]}} if name == selected else {})}
            for name in ("model-a", "model-b")
        ]}
    monkeypatch.setattr("core.model_catalog.runtime_call", metadata)
    refresh(connection)
    selected = "model-b"
    result = refresh(connection, selected)
    models = {item["identifier"]: item for item in result["items"]}
    assert models["model-a"]["capabilities"]["reasoning_efforts"] == ["low", "high"]
    assert models["model-b"]["capabilities"]["reasoning_efforts"] == ["low", "high"]


@pytest.mark.parametrize("outcome", ["success", "failure", "malformed", "metadata-error"])
def test_runtime_refreshes_after_outcomes_without_replacing_them(monkeypatch, outcome):
    def execute(payload):
        if outcome == "malformed":
            raise server.HTTPException(502, "Invalid response")
        return {"failure": {"kind": "QUOTA_EXHAUSTED"}} if outcome == "failure" else {"output": {"ok": True}}
    calls = []
    def status(*args, **kwargs):
        calls.append(kwargs)
        if outcome == "metadata-error":
            raise RuntimeError("synthetic private failure")
        return {"quota_status": {"state": "available"}, "quota_windows": {"weekly": {"used_percent": 25}}}
    monkeypatch.setattr(server, "execute_run", execute)
    monkeypatch.setattr(server, "connection_status", status)
    payload = server.RunIn(request_id=uuid.uuid4(), workspace="/unused", prompt="unused", schema={}, timeout=2)
    result = server.run(payload)
    assert calls == [{"include_quota": True}]
    assert result["quota_status"]["state"] == ("error" if outcome == "metadata-error" else "available")
    if outcome in {"success", "metadata-error"}:
        assert result["output"] == {"ok": True}
    else:
        assert result["failure"]["kind"] == ("ERROR" if outcome == "malformed" else "QUOTA_EXHAUSTED")
    assert "private" not in json.dumps(result)


@pytest.mark.django_db
def test_known_reset_bypasses_throttle_but_shared_refresh_is_then_cached(client, monkeypatch):
    now = timezone.now()
    identity = AIIdentity.objects.create(agent="codex", status="CONNECTED", quota_windows={
        "weekly": {"used_percent": 100, "resets_at": (now-timedelta(seconds=5)).isoformat()},
        "_status": {"state": "available", "checked_at": (now-timedelta(seconds=20)).isoformat()}})
    first = AIConnection.objects.create(agent="codex", identity=identity)
    second = AIConnection.objects.create(agent="codex", identity=identity)
    calls = []
    def read(*args, **kwargs):
        calls.append(args)
        return {"status": "CONNECTED", "quota_status": {"state": "available"}, "quota_windows": {"weekly": {"used_percent": 0}}}
    monkeypatch.setattr("core.ai_api.runtime_call", read)
    assert client.post(f"/api/ai-connections/{first.pk}/quota/refresh").json()["quota_refresh_state"] == "refreshed"
    assert client.post(f"/api/ai-connections/{second.pk}/quota/refresh").json()["quota_refresh_state"] == "cached"
    assert len(calls) == 1
