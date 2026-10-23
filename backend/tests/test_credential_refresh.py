import json
import stat

import pytest

from runtime.auth import publish_refresh
from runtime.vault import PREFIX
from runtime.vault import read as read_credential


@pytest.fixture(autouse=True)
def vault_key(monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "fixture-vault-key")


def credentials(token, account="same-account"):
    return json.dumps(
        {
            "tokens": {
                "access_token": token,
                "refresh_token": "refresh-" + token,
                "id_token": "id-" + token,
                "account_id": account,
            },
            "last_refresh": "fixture",
        }
    ).encode()


def test_official_token_rotation_persists_for_future_sessions(tmp_path):
    directory = tmp_path / "codex"
    directory.mkdir()
    original = credentials("old")
    candidate = credentials("new")
    path = directory / "auth.json"
    path.write_bytes(original)
    assert publish_refresh(tmp_path, "codex", original, candidate)
    assert read_credential(path) == candidate
    assert path.read_bytes().startswith(PREFIX)
    assert candidate not in path.read_bytes()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_refresh_cannot_overwrite_new_login_or_change_account(tmp_path):
    directory = tmp_path / "codex"
    directory.mkdir()
    path = directory / "auth.json"
    original = credentials("old")
    path.write_bytes(credentials("reconnected"))
    assert not publish_refresh(tmp_path, "codex", original, credentials("rotation"))
    assert path.read_bytes() == credentials("reconnected")
    path.write_bytes(original)
    assert not publish_refresh(tmp_path, "codex", original, credentials("foreign", "other-account"))
    assert path.read_bytes() == original


def test_claude_refresh_keeps_subscription_and_scope(tmp_path):
    directory = tmp_path / "claude"
    directory.mkdir()
    original = json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": "old",
                "refreshToken": "old-refresh",
                "expiresAt": 1,
                "scopes": ["read"],
                "subscriptionType": "pro",
            }
        }
    ).encode()
    refreshed = json.loads(original)
    refreshed["claudeAiOauth"].update(accessToken="new", refreshToken="new-refresh", expiresAt=2)
    candidate = json.dumps(refreshed).encode()
    path = directory / ".credentials.json"
    path.write_bytes(original)
    assert publish_refresh(tmp_path, "claude", original, candidate)
    refreshed["claudeAiOauth"]["scopes"] = ["unexpected"]
    assert not publish_refresh(tmp_path, "claude", candidate, json.dumps(refreshed).encode())
