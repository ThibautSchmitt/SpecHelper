import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from runtime import server
from runtime.auth import account_key, identity_root, publish_refresh, subscription_credentials
from runtime.quota import codex_windows, rollout_windows
from runtime.vault import read as read_credential


@pytest.fixture(autouse=True)
def vault_key(monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "fixture-key")


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "test-v14-control")
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(server, "CREDENTIALS", tmp_path / "credentials")
    request = str(uuid.uuid4())
    workspace = server.DATA / "analysis-workspaces" / request
    workspace.mkdir(parents=True)
    (server.DATA / "requests" / request / "attachments").mkdir(parents=True)
    payload = {
        "request_id": request,
        "workspace": str(workspace),
        "prompt": "Read only",
        "schema": {},
        "timeout": 2,
    }
    return TestClient(server.app), payload


def oauth(identity, provider="codex"):
    directory = identity_root(server.CREDENTIALS, identity) / provider
    directory.mkdir(parents=True)
    value = (
        {
            "tokens": {
                "access_token": "synthetic-" + str(identity),
                "account_id": "account-" + str(identity),
            }
        }
        if provider == "codex"
        else {"claudeAiOauth": {"accessToken": "synthetic-" + str(identity)}}
    )
    path = directory / ("auth.json" if provider == "codex" else ".credentials.json")
    path.write_text(json.dumps(value))
    return path


def test_runtime_credential_namespaces_and_selected_models_are_isolated(isolated_runtime):
    client, payload = isolated_runtime
    identities = [str(uuid.uuid4()), str(uuid.uuid4())]
    for identity in identities:
        oauth(identity)
    observed = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            self.session = Path(command[command.index("--bind") + 1])
            value = json.loads((self.session / "codex" / "auth.json").read_text())
            observed.append(
                (value["tokens"]["access_token"], command[command.index("--model") + 1])
            )
            assert "OPENAI_API_KEY" not in kwargs["env"]
            assert "ANTHROPIC_API_KEY" not in kwargs["env"]

        def communicate(self, *args, **kwargs):
            (self.session / "result.json").write_text('{"ok":true}')
            return json.dumps(
                {"type": "thread.started", "thread_id": str(uuid.uuid4())}
            ).encode(), None

    with patch("runtime.server.subprocess.Popen", Process):
        for identity in identities:
            response = client.post(
                "/run",
                json={
                    **payload,
                    "identity_id": identity,
                    "context_id": str(uuid.uuid4()),
                    "model": "accepted-model",
                },
                headers={"Authorization": "Bearer test-v14-control"},
            )
            assert response.status_code == 200
            assert response.json()["model"] == "accepted-model"
    assert len(observed) == 2
    assert len({token for token, _ in observed}) == 2
    assert all(model == "accepted-model" for _, model in observed)
    assert all(not token.startswith("synthetic-") for token, _ in observed)


def test_runtime_rejects_api_key_mode_instead_of_billed_fallback(isolated_runtime):
    client, payload = isolated_runtime
    identity = str(uuid.uuid4())
    path = oauth(identity)
    path.write_text(
        json.dumps(
            {
                "OPENAI_API_KEY": "synthetic-billed-key",
                "tokens": {"access_token": "synthetic-oauth"},
            }
        )
    )
    with patch("runtime.server.subprocess.Popen") as process:
        response = client.post(
            "/run",
            json={**payload, "identity_id": identity},
            headers={"Authorization": "Bearer test-v14-control"},
        )
    assert response.json() == {
        "failure": {"kind": "AUTH_ERROR"},
        "context_usage": [],
        "context_audit": "unavailable",
    }
    process.assert_not_called()


def test_claude_explicit_model_is_passed_without_api_key_environment(isolated_runtime):
    client, payload = isolated_runtime
    identity = str(uuid.uuid4())
    oauth(identity, "claude")
    metadata = identity_root(server.CREDENTIALS, identity) / "claude/.claude.json"
    original = {
        "oauthAccount": {
            "accountUuid": "fixture-account",
            "organizationUuid": "fixture-organization",
        },
        "hasCompletedOnboarding": True,
        "primaryApiKey": "synthetic-paid-key",
        "apiKeyHelper": "do-not-execute",
        "mcpServers": {"unsafe": {"command": "do-not-execute"}},
        "hooks": {"SessionStart": "do-not-execute"},
    }
    metadata.write_text(json.dumps(original))
    commands = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            commands.append(command)
            session = Path(command[command.index("--bind") + 1])
            copied = json.loads((session / "claude/.claude.json").read_text())
            assert copied == {
                "oauthAccount": original["oauthAccount"],
                "hasCompletedOnboarding": True,
            }
            assert "synthetic-paid-key" not in json.dumps(copied)

        def communicate(self, *args, **kwargs):
            return json.dumps(
                {
                    "structured_output": {"ok": True},
                    "session_id": str(uuid.uuid4()),
                    "modelUsage": {"claude-accepted": {}},
                    "usage": {},
                }
            ).encode(), None

    with patch("runtime.server.subprocess.Popen", Process):
        response = client.post(
            "/run",
            json={
                **payload,
                "identity_id": identity,
                "agent": "claude",
                "model": "claude-accepted",
            },
            headers={"Authorization": "Bearer test-v14-control"},
        )
    assert response.json()["model"] == "claude-accepted"
    assert commands[0][commands[0].index("--model") + 1] == "claude-accepted"
    assert json.loads(metadata.read_text()) == original


def test_model_failure_is_typed_and_never_leaks_provider_text():
    failure = json.dumps(
        {"type": "turn.failed", "error": {"message": "model_not_found private-account-token"}}
    ).encode()
    assert server.classify_failure(failure) == {"kind": "MODEL_UNAVAILABLE"}


def test_namespaced_refresh_never_changes_other_account_or_legacy(tmp_path):
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    original = json.dumps({"tokens": {"access_token": "old", "account_id": "stable"}}).encode()
    candidate = json.dumps({"tokens": {"access_token": "new", "account_id": "stable"}}).encode()
    for identity in (first, second, None):
        directory = identity_root(tmp_path, identity) / "codex"
        directory.mkdir(parents=True)
        (directory / "auth.json").write_bytes(original)
    assert publish_refresh(identity_root(tmp_path, first), "codex", original, candidate)
    assert read_credential(identity_root(tmp_path, first) / "codex/auth.json") == candidate
    assert (identity_root(tmp_path, second) / "codex/auth.json").read_bytes() == original
    assert (tmp_path / "codex/auth.json").read_bytes() == original


def test_account_fingerprint_requires_actual_provider_id_and_never_exposes_it(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": "opaque-token", "account_id": "account-uuid"}})
    )
    key = account_key(tmp_path, "codex")
    assert len(key) == 64 and "account-uuid" not in key
    (tmp_path / "auth.json").write_text(json.dumps({"tokens": {"access_token": "opaque-token"}}))
    assert account_key(tmp_path, "codex") == ""
    assert subscription_credentials(tmp_path, "codex")
    with pytest.raises(ValueError):
        identity_root(tmp_path, "../other-account")


def test_official_codex_rollout_quota_windows_are_current_scoped_and_typed(tmp_path):
    identifier, other = str(uuid.uuid4()), str(uuid.uuid4())
    started = datetime.now(UTC)
    directory = tmp_path / "sessions/2026/10/22"
    directory.mkdir(parents=True)

    def event(timestamp, used):
        return {
            "timestamp": timestamp.isoformat(),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": used,
                        "window_minutes": 300,
                        "resets_at": 1900000000,
                    },
                    "secondary": {
                        "used_percent": 100,
                        "window_minutes": 10080,
                        "resets_at": 1900100000,
                    },
                },
            },
        }

    path = directory / ("rollout-" + identifier + ".jsonl")
    path.write_text(
        json.dumps(event(started - timedelta(minutes=1), 99))
        + "\n"
        + json.dumps(event(started + timedelta(seconds=1), 30))
        + "\n"
    )
    (directory / ("rollout-" + other + ".jsonl")).write_text(json.dumps(event(started, 80)))
    windows = rollout_windows(tmp_path, identifier, started)
    assert windows["session"]["used_percent"] == 30
    assert windows["weekly"]["exhausted"] is True
    assert windows["weekly"]["resets_at"].endswith("+00:00")
    assert rollout_windows(tmp_path, str(uuid.uuid4()), started) == {}
    assert codex_windows({"primary": {"used_percent": 50, "window_minutes": None}}) == {}
    assert codex_windows({"primary": {"used_percent": float("nan"), "window_minutes": 300}}) == {}
    assert codex_windows({"primary": {"used_percent": True, "window_minutes": 300}}) == {}
