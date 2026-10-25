"""Official Google sign-in protocol with controlled CLI credentials, never real accounts."""

import json
import os
import stat

import pytest

from core.login import TerminalLogin, browser_details
from runtime.auth import Logins
from runtime.vault import PREFIX, read


def test_google_authorization_url_is_host_scoped_and_never_accepts_a_deceptive_host():
    url = (
        "https://accounts.google.com/o/oauth2/auth?state=fixture&code_challenge=fixture"
        "&client_id=fixture.apps.googleusercontent.com&redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback&response_type=code"
    )
    assert browser_details("antigravity", "", url) == {
        "verification_uri": url, "user_code": "", "input_required": True,
    }
    for candidate in ("https://accounts.google.com.attacker.invalid/login", "https://user@accounts.google.com/login"):
        assert not browser_details("antigravity", "", candidate)["verification_uri"]


def test_terminal_wrapping_preserves_the_complete_google_oauth_url_and_pkce():
    chunks = [
        "https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=fixture",
        ".apps.googleusercontent.com&code_challenge=fixture-challenge&code_chall",
        "enge_method=S256&redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback&re",
        "sponse_type=code&scope=openid+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.email",
        "&state=fixture-state",
    ]
    output = "Open the URL below:\r\n ──────────\r\n " + "\r\n ".join(chunks) + "\r\n ──────────\r\n"
    assert browser_details("antigravity", output)["verification_uri"] == "".join(chunks)
    for incomplete in (chunks[0], "\r\n ".join(chunks[:3])):
        assert not browser_details("antigravity", incomplete)["verification_uri"]


def test_native_google_login_stops_exact_cli_and_seals_only_its_fresh_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "fixture-v27-control")
    monkeypatch.setattr("runtime.antigravity_auth.inspect_cli", lambda: {"state": "supported"})
    marker = tmp_path / "finished"
    client = tmp_path / "agy"
    client.write_text("""#!/usr/bin/env python3
import json, os, time
from pathlib import Path
assert 'GEMINI_API_KEY' not in os.environ
assert 'GOOGLE_API_KEY' not in os.environ
assert os.environ['DBUS_SESSION_BUS_ADDRESS'] == 'unix:path=/nonexistent'
assert os.environ['SSH_CONNECTION']
home=Path(os.environ['HOME'])
path=home/'.gemini/antigravity-cli/antigravity-oauth-token'
path.parent.mkdir(parents=True)
path.write_text(json.dumps({'auth_method':'consumer','token':{
'access_token':'fixture-private-access','refresh_token':'fixture-private-refresh',
'token_type':'Bearer','expiry':'2099-01-01T00:00:00Z'}}))
print('Waiting with an authenticated account.',flush=True)
time.sleep(30)
""")
    client.chmod(client.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(tmp_path) + ":" + os.environ["PATH"])
    monkeypatch.setenv("GEMINI_API_KEY", "ambient-must-not-be-inherited")
    monkeypatch.setattr(TerminalLogin, "start", lambda self: self.run())
    root = tmp_path / "credentials"
    result = Logins(lambda: root).start("fixture", "antigravity")
    assert result["status"] == "CONNECTED"
    assert not marker.exists()
    sealed = root / "antigravity/auth.json"
    assert sealed.read_bytes().startswith(PREFIX)
    assert b"fixture-private-access" not in sealed.read_bytes()
    credential = json.loads(read(sealed))
    assert credential["auth_mode"] == "google_oauth"
    assert credential["credential"]["token"]["access_token"] == "fixture-private-access"
    assert "fixture-private" not in json.dumps(result)


def test_google_code_requires_a_live_expected_prompt():
    login = TerminalLogin("antigravity", lambda *_: {})
    with pytest.raises(ValueError, match="No confirmation code"):
        login.submit("fixture-code")


def test_google_code_uses_the_native_enter_key_without_affecting_claude(monkeypatch):
    written = []
    monkeypatch.setattr("core.login.os.write", lambda fd, value: written.append((fd, value)))
    for provider, ending in (("antigravity", b"\r"), ("claude", b"\n")):
        login = TerminalLogin(provider, lambda *_: {})
        login.terminal = 123
        login.state.update(status="AWAITING_USER", input_required=True)
        login.submit("fixture-code")
        assert written[-1] == (123, b"fixture-code" + ending)
        assert login.public()["message"] == "Verifying connection…"
