import json
import os
import time

import pytest

from core.login import ACTIVE, TerminalLogin, browser_details
from runtime.auth import Logins


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Login did not reach expected state")


@pytest.mark.parametrize(
    "provider,text,url,code",
    [
        (
            "github",
            "\x1b[32mFirst copy your code: A1B2-C3D4\x1b[0m\nhttps://github.com/login/device",
            "https://github.com/login/device",
            "A1B2-C3D4",
        ),
        (
            "codex",
            "https://auth.openai.com/codex/device\nABCDE-FGHIJ",
            "https://auth.openai.com/codex/device",
            "ABCDE-FGHIJ",
        ),
        (
            "claude",
            "https://claude.ai/oauth/authorize?code=true&state=fixture",
            "https://claude.ai/oauth/authorize?code=true&state=fixture",
            "",
        ),
    ],
)
def test_official_login_output_only_exposes_browser_steps(provider, text, url, code):
    state = browser_details(provider, text)
    assert state["verification_uri"] == url
    assert state["user_code"] == code
    assert state["input_required"] == (provider == "claude")


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://github.com.evil.invalid/login/device",
        "https://evil.invalid/auth",
        "https://name:secret@github.com/login/device",
    ],
)
def test_untrusted_login_links_are_never_exposed(url):
    assert browser_details("github", url)["verification_uri"] == ""


def executable(tmp_path, monkeypatch, name, code):
    path = tmp_path / name
    path.write_text("#!/usr/bin/env python3\n" + code)
    path.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])


def test_github_login_handles_official_prompts_without_terminal_input(tmp_path, monkeypatch):
    executable(
        tmp_path,
        monkeypatch,
        "gh",
        """import os, pathlib, time
assert not os.isatty(0)
print("First copy your one-time code: A1B2-C3D4",flush=True)
print("https://github.com/login/device",flush=True)
time.sleep(.05)
pathlib.Path(os.environ['GH_CONFIG_DIR'],'hosts.yml').write_text('fixture-token')
""",
    )
    events = []

    def complete(home, env):
        assert (home / "github/hosts.yml").read_text() == "fixture-token"
        return {"account": "fixture"}

    login = TerminalLogin("github", complete, events.append, ttl=5)
    login.start()
    until(lambda: login.public()["status"] not in ACTIVE)
    assert login.public()["status"] == "CONNECTED"
    assert any(event["user_code"] == "A1B2-C3D4" for event in events)
    assert "fixture-token" not in json.dumps(events)


def test_claude_login_accepts_confirmation_and_persists_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "fixture-login-vault-key")
    executable(
        tmp_path,
        monkeypatch,
        "claude",
        """import json, os, pathlib
print("https://claude.ai/oauth/authorize?code=true&state=fixture",flush=True)
assert input()=="code#state"
pathlib.Path(os.environ['CLAUDE_CONFIG_DIR'],'.credentials.json').write_text(json.dumps({'claudeAiOauth':{'accessToken':'fixture-secret'}}))
""",
    )
    manager = Logins(lambda: tmp_path / "credentials")
    manager.start("attempt", "claude")
    until(lambda: manager.get("attempt")["input_required"])
    assert manager.get("attempt")["status"] == "AWAITING_USER"
    manager.submit("attempt", "code#state")
    until(lambda: manager.get("attempt")["status"] not in ACTIVE)
    assert manager.get("attempt")["status"] == "CONNECTED"
    stored = tmp_path / "credentials/claude/.credentials.json"
    assert stored.exists() and stored.stat().st_mode & 0o777 == 0o600
    from runtime.vault import read as read_credential

    assert b"fixture-secret" not in stored.read_bytes()
    assert json.loads(read_credential(stored))["claudeAiOauth"]["accessToken"] == "fixture-secret"
    assert "fixture-secret" not in json.dumps(manager.get("attempt"))


def test_pending_login_is_cancelled_and_process_stops(tmp_path, monkeypatch):
    executable(
        tmp_path,
        monkeypatch,
        "codex",
        """import time
print('https://auth.openai.com/codex/device ABCDE-FGHIJ',flush=True)
time.sleep(60)
""",
    )
    login = TerminalLogin("codex", lambda home, env: {}, ttl=5)
    login.start()
    until(lambda: login.public()["status"] == "AWAITING_USER")
    login.cancel()
    until(lambda: login.public()["status"] == "CANCELLED")
    assert login.process.poll() is not None


def test_confirmation_does_not_accept_shell_or_multiline_input():
    login = TerminalLogin("claude", lambda home, env: {})
    login.state.update(status="AWAITING_USER", input_required=True)
    with pytest.raises(ValueError, match="Invalid"):
        login.submit("code\nrm -rf /")
