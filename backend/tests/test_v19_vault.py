"""CLI credential migration fails closed and preserves existing OAuth data."""

import json
import os
import stat
from unittest.mock import patch

import pytest

from runtime import vault
from runtime.auth import account_key, connection_status, subscription_credentials


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "synthetic-vault-key-one")


def test_startup_seals_legacy_and_named_identities_without_changing_identity(tmp_path):
    credentials = {
        "codex/auth.json": {"tokens": {"access_token": "private-oauth-codex", "account_id": "account-one"}},
        "identities/fixture/claude/.credentials.json": {"claudeAiOauth": {"accessToken": "private-oauth-claude"}},
        "identities/fixture/claude/.claude.json": {"oauthAccount": {"accountUuid": "account-two"}},
    }
    for name, data in credentials.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    identity = account_key(tmp_path / "codex", "codex")
    assert vault.seal(tmp_path) == 3
    assert vault.seal(tmp_path) == 0
    assert account_key(tmp_path / "codex", "codex") == identity
    for name, data in credentials.items():
        path = tmp_path / name
        assert path.read_bytes().startswith(vault.PREFIX)
        assert b"private-oauth" not in path.read_bytes()
        assert json.loads(vault.read(path)) == data
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert subscription_credentials(tmp_path / "codex", "codex")
    assert subscription_credentials(tmp_path / "identities/fixture/claude", "claude")


def test_atomic_seal_failure_keeps_original_credentials_and_removes_temporary(tmp_path):
    path = tmp_path / "auth.json"
    original = b'{"tokens":{"access_token":"synthetic-private-value"}}'
    path.write_bytes(original)
    with patch("runtime.vault.os.replace", side_effect=OSError("synthetic failure")):
        with pytest.raises(OSError):
            vault.seal(tmp_path)
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["auth.json"]


def test_wrong_key_or_modified_ciphertext_never_returns_plaintext(tmp_path):
    path = tmp_path / "auth.json"
    vault.write(path, b'{"synthetic":"private-value"}')
    original = path.read_bytes()
    with pytest.raises(ValueError, match="does not match"):
        vault.read(path, token="different-key")
    assert path.read_bytes() == original
    path.write_bytes(original[:-8] + b"tampered")
    with pytest.raises(ValueError, match="does not match"):
        vault.read(path)


def test_symlink_and_oversized_credentials_cannot_be_materialized(tmp_path):
    private = tmp_path / "private"
    private.write_bytes(b"parent-private")
    link = tmp_path / "auth.json"
    link.symlink_to(private)
    with pytest.raises((ValueError, OSError)):
        vault.read(link)
    with pytest.raises(ValueError):
        vault.write(link, b"replacement")
    assert private.read_bytes() == b"parent-private"
    with pytest.raises(ValueError):
        vault.write(tmp_path / "too-large", b"a" * (512 * 1024 + 1))


def test_status_materializes_only_private_temporary_files_and_removes_them(tmp_path):
    path = tmp_path / "codex/auth.json"
    plaintext = b'{"tokens":{"access_token":"private-status-token","account_id":"same-account"}}'
    vault.write(path, plaintext)
    homes = []

    def status(command, env, **kwargs):
        from pathlib import Path

        home = Path(env["CODEX_HOME"])
        homes.append(home)
        assert home != path.parent
        assert stat.S_IMODE(home.stat().st_mode) == 0o700
        assert stat.S_IMODE((home / "auth.json").stat().st_mode) == 0o600
        assert (home / "auth.json").read_bytes() == plaintext
        assert "RUNTIME_TOKEN" not in env
        return type("Result", (), {"returncode": 0})()

    with patch("runtime.auth.subprocess.run", side_effect=status):
        assert connection_status(tmp_path, "codex")["status"] == "CONNECTED"
    assert homes and all(not home.exists() for home in homes)
    assert path.read_bytes().startswith(vault.PREFIX)


def test_missing_key_does_not_replace_existing_credentials(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_bytes(b"legacy-oauth")
    monkeypatch.delenv("RUNTIME_TOKEN")
    monkeypatch.setenv("CONTROL_TOKEN_FILE", os.fspath(tmp_path / "missing-key"))
    with pytest.raises(ValueError, match="key unavailable"):
        vault.write(path, b"new-oauth")
    assert path.read_bytes() == b"legacy-oauth"


def test_legacy_session_copies_are_sealed_and_untrusted_invalid_copies_cannot_block_startup(tmp_path):
    root = tmp_path / "sessions"
    home = root / "fixture/codex"
    home.mkdir(parents=True)
    credential = home / "auth.json"
    original = b'{"tokens":{"access_token":"old-session-private-oauth"}}'
    credential.write_bytes(original)
    invalid = home / ".claude.json"
    invalid.write_bytes(b"untrusted non-json session state")
    oversized = home / ".credentials.json"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    other = root / "other/codex"
    other.mkdir(parents=True)
    private = tmp_path / "outside"
    private.write_bytes(b"must not change")
    (other / "auth.json").symlink_to(private)
    assert vault.seal(root, validate_json=False) == 2
    assert vault.read(credential) == original
    assert b"old-session-private-oauth" not in credential.read_bytes()
    assert vault.read(invalid) == b"untrusted non-json session state"
    assert not oversized.exists()
    assert not (other / "auth.json").exists()
    assert private.read_bytes() == b"must not change"
    assert vault.seal(root, validate_json=False) == 0
