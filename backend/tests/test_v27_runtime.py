"""Trusted credential setup and exact Gemini relay boundaries, without real accounts."""

import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from runtime import server
from runtime.antigravity_auth import MODE, credentials, metadata_environment, prepare_session
from runtime.broker import MAX_BODY, Broker, read_chunked_body
from runtime.vault import PREFIX


@pytest.fixture
def runtime_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "fixture-v27-control")
    monkeypatch.setattr(server, "CREDENTIALS", tmp_path / "credentials")
    monkeypatch.setattr(
        "runtime.antigravity_auth.inspect_cli",
        lambda: {"state": "supported", "reason": "", "version": "1.4.7"},
    )
    return TestClient(server.app)


def test_explicit_identity_credential_is_encrypted_and_not_reported_as_verified_access(runtime_client):
    identity = str(uuid.uuid4())
    key = "fixture-only-explicit-gemini-key"
    response = runtime_client.post(
        "/auth/api-key",
        headers={"Authorization": "Bearer fixture-v27-control"},
        json={"provider": "antigravity", "identity_id": identity, "api_key": key, "confirm_billing": True},
    )
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "CONNECTED"
    assert value["access_verified"] is False and value["usage"] == "UNKNOWN"
    assert value["quota_status"]["state"] == "unavailable"
    assert key not in response.text
    directory = server.CREDENTIALS / "identities" / identity / "antigravity"
    assert (directory / "auth.json").read_bytes().startswith(PREFIX)
    assert key.encode() not in (directory / "auth.json").read_bytes()
    assert credentials(directory) == {"auth_mode": MODE, "api_key": key}


@pytest.mark.parametrize("change", [
    {"confirm_billing": 1}, {"confirm_billing": "true"}, {"confirm_billing": False},
    {"confirm_billing": None}, {"provider": "codex"}, {"extra_secret": "unrecognized"},
    {"api_key": {"nested": "fixture-sensitive-input"}}, {"identity_id": "invalid"},
])
def test_malformed_credential_input_is_not_echoed(runtime_client, change):
    value = {
        "provider": "antigravity", "identity_id": str(uuid.uuid4()),
        "api_key": "fixture-sensitive-input", "confirm_billing": True,
        **change,
    }
    response = runtime_client.post(
        "/auth/api-key", json=value,
        headers={"Authorization": "Bearer fixture-v27-control"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid credential configuration."}
    assert "fixture-sensitive-input" not in response.text
    assert not list(server.CREDENTIALS.rglob("auth.json"))


def test_credential_setup_requires_runtime_authorization(runtime_client):
    response = runtime_client.post("/auth/api-key", json={
        "provider": "antigravity", "identity_id": str(uuid.uuid4()),
        "api_key": "fixture-sensitive-input", "confirm_billing": True,
    })
    assert response.status_code == 401 and "fixture-sensitive-input" not in response.text


def test_missing_native_browser_client_fails_without_importing_host_authentication(runtime_client, monkeypatch):
    monkeypatch.setattr("runtime.antigravity_auth.inspect_cli", lambda: {"state": "unavailable"})
    response = runtime_client.post("/auth/start", json={
        "provider": "antigravity", "attempt_id": str(uuid.uuid4()),
        "identity_id": str(uuid.uuid4()),
    }, headers={"Authorization": "Bearer fixture-v27-control"})
    assert response.status_code == 200
    assert response.json()["status"] == "ERROR"
    assert response.json()["message"] == "Antigravity CLI is unavailable or incompatible."
    assert not response.json()["verification_uri"]
    assert not response.json()["input_required"]


@pytest.mark.parametrize("path", [
    "/antigravity/v1beta/models/gemini-fixture:generateContent",
    "/antigravity/v1beta/models/gemini-fixture:streamGenerateContent?alt=sse",
    "/antigravity/v1beta/models/gemini-fixture:countTokens",
])
def test_gemini_destination_and_credential_are_selected_by_the_trusted_broker(path):
    broker = Broker("antigravity", {"api_key": "fixture-real-key"}, 10)
    assert broker.destination("POST", path) == (
        "https://generativelanguage.googleapis.com" + path.removeprefix("/antigravity")
    )
    headers = broker.headers({
        "Authorization": "Bearer malicious", "Host": "private.invalid",
        "x-goog-api-key": "attacker-key", "Content-Type": "application/json",
    })
    assert headers["x-goog-api-key"] == "fixture-real-key"
    assert "Authorization" not in headers and "Host" not in headers
    assert "fixture-real-key" not in json.dumps(broker.redact({"nested": ["fixture-real-key"]}))


@pytest.mark.parametrize("path", [
    "https://private.invalid/v1beta/models/x:generateContent",
    "//private.invalid/path", "/antigravity/v1beta/models/x:generateContent?key=attacker",
    "/antigravity/v1beta/models/x:generateContent?alt=sse&url=https://private.invalid",
    "/antigravity/v1beta/models/x%2fy:generateContent",
    "/antigravity/v1beta/models/../secret:generateContent",
    "/antigravity/v1beta/files", "/antigravity/v1beta/models/x:delete",
    "/antigravity/v1beta/models/x:generateContent#fragment",
])
def test_gemini_broker_rejects_arbitrary_paths_targets_and_query_parameters(path):
    broker = Broker("antigravity", {"api_key": "fixture-real-key"}, 10)
    assert broker.destination("POST", path) is None
    assert broker.destination("GET", path) is None


def test_cli_metadata_ignores_ambient_keys_and_session_policy_is_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ambient-key-must-not-be-inherited")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://untrusted.invalid")
    env = metadata_environment(tmp_path / "metadata")
    assert "GEMINI_API_KEY" not in env and "GOOGLE_GEMINI_BASE_URL" not in env
    grants = prepare_session(tmp_path / "session")
    assert "command(git)" in grants["allow"] and "command(curl)" in grants["allow"]
    assert grants["deny"] == ["write_file(*)"]
    assert not any("skip" in value or "*" in value for value in grants["allow"])
    settings = json.loads((tmp_path / "session/.gemini/antigravity-cli/settings.json").read_text())
    assert settings["modelProvider"] == "gemini" and settings["trustedWorkspaces"] == ["/workspace"]


def test_common_google_key_shape_is_redacted_even_outside_its_identity_context():
    from core.sensitive_data import redact

    synthetic = "AIza" + "x" * 35
    result = redact({"need": "Never send " + synthetic + " to another assistant."}, [])
    assert synthetic not in json.dumps(result)
    assert result["need"] == "Never send [REDACTED] to another assistant."


def oauth_broker():
    return Broker("antigravity", {
        "auth_mode": "google_oauth",
        "credential": {"auth_method": "consumer", "token": {
            "access_token": "fixture-private-oauth-access",
            "refresh_token": "fixture-private-oauth-refresh",
        }},
    }, 10)


@pytest.mark.parametrize("method", [
    "loadCodeAssist", "fetchAvailableModels", "listExperiments", "fetchUserInfo",
    "generateContent", "streamGenerateContent", "countTokens",
])
def test_personal_oauth_relay_keeps_native_protocol_and_replaces_only_synthetic_auth(method):
    broker = oauth_broker()
    path = "/antigravity-oauth/v1internal:" + method
    assert broker.destination("POST", path) == (
        "https://daily-cloudcode-pa.googleapis.com/v1internal:" + method
    )
    headers = broker.headers({
        "Authorization": "Bearer " + broker.token,
        "x-goog-api-key": "caller-cannot-switch-billing-mode",
        "Host": "attacker.invalid", "Content-Type": "application/json",
    })
    assert headers == {
        "Content-Type": "application/json",
        "Authorization": "Bearer fixture-private-oauth-access",
    }
    assert broker.redact({"data": [
        "fixture-private-oauth-access", "fixture-private-oauth-refresh",
    ]}) == {"data": ["[REDACTED]", "[REDACTED]"]}


@pytest.mark.parametrize("path", [
    "/antigravity/v1beta/models/gemini-fixture:generateContent",
    "/antigravity-oauth/v1internal:onboardUser",
    "/antigravity-oauth/v1internal:loadCodeAssist?key=caller",
    "/antigravity-oauth/v1internal:updateUserInfo",
    "/antigravity-oauth/v1internal:generateContent?url=https://private.invalid",
    "/antigravity-oauth/v1internal:generateContent#fragment",
    "/antigravity-oauth/v1internal:%67enerateContent",
    "https://private.invalid/v1internal:generateContent",
])
def test_personal_relay_cannot_switch_to_paid_api_or_mutate_account_or_choose_a_target(path):
    broker = oauth_broker()
    assert broker.destination("POST", path) is None
    assert broker.destination("GET", path) is None


def test_native_chunked_request_has_strict_framing_and_an_unchanged_body_limit():
    assert read_chunked_body(io.BytesIO(b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n")) == b"abcde"
    for value in (
        b"3\nabc\n0\n\n", b"3;extension=1\r\nabc\r\n0\r\n\r\n",
        b"0\r\nHost: attacker.invalid\r\n\r\n", b"3\r\na", b"not-hex\r\n",
        (format(MAX_BODY + 1, "x") + "\r\n").encode(),
    ):
        with pytest.raises(ValueError):
            read_chunked_body(io.BytesIO(value))


@pytest.mark.parametrize("kind", ["AUTH_ERROR", "QUOTA_EXHAUSTED", "MODEL_UNAVAILABLE", "TIMEOUT"])
def test_execution_preflight_preserves_metadata_failure_before_any_provider_turn(
    runtime_client, tmp_path, monkeypatch, kind,
):
    from runtime.vault import write

    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SESSIONS", tmp_path / "sessions")
    request_id = uuid.uuid4()
    workspace = server.DATA / "analysis-workspaces" / str(request_id)
    workspace.mkdir(parents=True)
    write(server.CREDENTIALS / "antigravity/auth.json", json.dumps({
        "auth_mode": MODE, "api_key": "fixture-explicit-key-only",
    }).encode())
    monkeypatch.setattr("runtime.model_discovery.discover", lambda *_: {
        "state": "unavailable", "reason": "refresh_failed", "items": [],
        "failure": {"kind": kind},
    })
    result = server.run(server.RunIn(
        request_id=request_id, agent="antigravity", model="gemini-fixture",
        workspace=str(workspace), prompt="Fixture request.", schema={"type": "object"}, timeout=5,
    ))
    assert result["failure"] == {"kind": kind}
    assert result.get("timed_out", False) == (kind == "TIMEOUT")
    assert not list(server.SESSIONS.rglob("antigravity-oauth-token"))
