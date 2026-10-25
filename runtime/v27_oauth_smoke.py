"""Native personal OAuth transport with synthetic credentials and loopback fixtures only."""
import json
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx

from runtime import server
from runtime.antigravity import PINNED_VERSION, cli_status, discover_models
from runtime.antigravity_auth import metadata_environment, read_oauth_profile
from runtime.auth import Logins
from runtime.vault import write

MODEL = "gemini-3.8-flash-medium"
PROFILE = {"auth_method": "consumer", "token": {
    "access_token": "synthetic-trusted-only-access", "refresh_token": "synthetic-trusted-only-refresh",
    "token_type": "Bearer", "expiry": "2099-01-01T00:00:00Z",
}}


def run_probe(root):
    observations, tool_replies = [], []

    def respond(path, body):
        method = path.split(":")[-1].split("?")[0]
        observations.append(method)
        if method == "loadCodeAssist":
            return {"currentTier": {"id": "free-tier"}, "cloudaicompanionProject": "synthetic-project"}
        if method == "fetchAvailableModels":
            return {"models": {MODEL: {"displayName": "Synthetic Gemini", "model": "MODEL_CHAT_20706"}},
                    "defaultAgentModelId": MODEL,
                    "agentModelSorts": [{"displayName": "Synthetic", "groups": [
                        {"displayName": "Synthetic", "modelIds": [MODEL]}]}]}
        if method not in {"generateContent", "streamGenerateContent"}:
            return {}
        actual = body.get("request", body)
        replies = [p["functionResponse"] for c in actual.get("contents", [])
                   for p in c.get("parts", []) if "functionResponse" in p]
        tool_replies.extend(replies)
        if not actual.get("tools"):
            parts = [{"text": "Synthetic title"}]
        elif not replies:
            parts = [{"functionCall": {"name": "read_file", "args": {"Path": path}}}
                     for path in ("/workspace/evidence.txt", "/skills/v27-procedure/v2.md")]
        else:
            parts = [{"functionCall": {"name": "finish", "args": {"ok": True}}}]
        return {"response": {"candidates": [{"content": {"role": "model", "parts": parts},
                                            "finishReason": "STOP", "index": 0}]}}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            assert self.headers.get("Authorization") == "Bearer synthetic-trusted-only-access"
            payload = json.dumps(respond(self.path, body)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass

    metadata = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=metadata.serve_forever, daemon=True).start()

    def environment(home, api_key=None, oauth_profile=None):
        env = metadata_environment(home, api_key, oauth_profile)
        env["CLOUD_CODE_URL"] = "http://127.0.0.1:" + str(metadata.server_port)
        return env

    original_client = httpx.Client

    def upstream(request):
        assert request.url.host == "daily-cloudcode-pa.googleapis.com"
        assert request.headers.get("authorization") == "Bearer synthetic-trusted-only-access"
        body = respond(str(request.url), json.loads(request.content))
        if "streamGenerateContent" in str(request.url):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=("data: " + json.dumps(body) + "\n\n").encode())
        return httpx.Response(200, json=body)

    def client(*args, **kwargs):
        return original_client(*args, transport=httpx.MockTransport(upstream), **kwargs)

    try:
        with tempfile.TemporaryDirectory(prefix="v27-oauth-metadata-") as home:
            env = environment(home, oauth_profile=PROFILE)
            assert cli_status(env)["version"] == PINNED_VERSION
            catalogue = discover_models(env)
            assert catalogue["state"] == "supported", catalogue
            assert MODEL in {item["identifier"] for item in catalogue["items"]}
        server.DATA, server.SESSIONS, server.CREDENTIALS = root / "data", root / "sessions", root / "credentials"
        server.SESSIONS.mkdir()
        request_id, identity_id = uuid.uuid4(), uuid.uuid4()
        workspace = server.DATA / "analysis-workspaces" / str(request_id)
        workspace.mkdir(parents=True)
        (workspace / "evidence.txt").write_text("v27 synthetic source evidence")
        (server.DATA / "requests" / str(request_id) / "attachments").mkdir(parents=True)
        write(server.CREDENTIALS / "identities" / str(identity_id) / "antigravity/auth.json",
              json.dumps({"auth_mode": "google_oauth", "credential": PROFILE}).encode())
        payload = server.RunIn(request_id=request_id, attempt_id=uuid.uuid4(), identity_id=identity_id,
            agent="antigravity", model=MODEL, workspace=str(workspace), timeout=30,
            prompt="Read the source and skill files and return the required structured object.",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"], "additionalProperties": False},
            skill_definitions=[{"slug": "v27-procedure", "name": "Read-only procedure", "version": 2,
                "objective": "Inspect scoped sources.", "instructions": "v27 skill marker.",
                "required_capabilities": ["read_sources"]}])
        with patch("runtime.antigravity_auth.metadata_environment", environment), patch("runtime.broker.httpx.Client", client):
            result = server.run(payload)
        assert result.get("output") == {"ok": True}, result
        assert "v27 synthetic source evidence" in json.dumps(tool_replies), tool_replies
        assert "v27 skill marker" in json.dumps(tool_replies), tool_replies
        profiles = list(server.SESSIONS.rglob("antigravity-oauth-token"))
        assert profiles
        for path in profiles:
            profile = read_oauth_profile(path.parent.parent.parent)
            assert "synthetic-trusted-only" not in json.dumps(profile)
        return {"real_binary_version": PINNED_VERSION, "native_oauth_catalogue": True,
                "native_source_skill_reads_and_structured_output": True,
                "child_has_only_synthetic_broker_profile": True, "observed_endpoints": sorted(set(observations))}
    finally:
        metadata.shutdown()
        metadata.server_close()


def main():
    with tempfile.TemporaryDirectory(prefix="spechelper-v27-oauth-smoke-") as temporary:
        root = Path(temporary)
        logins = Logins(lambda: root / "login-vault")
        attempt = str(uuid.uuid4())
        logins.start(attempt, "antigravity")
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                value = logins.get(attempt)
                if value.get("verification_uri") or value["status"] == "ERROR":
                    break
                time.sleep(.1)
            assert value["status"] == "AWAITING_USER", value["status"]
            assert value["verification_uri"].startswith("https://accounts.google.com/")
            query = parse_qs(urlsplit(value["verification_uri"]).query)
            assert query["response_type"] == ["code"]
            assert all(query.get(key) for key in ("client_id", "redirect_uri", "state", "code_challenge"))
            assert value["input_required"] is True
            assert not (root / "login-vault").exists()
        finally:
            logins.cancel(attempt)
        deadline = time.monotonic() + 5
        while logins.get(attempt)["status"] != "CANCELLED" and time.monotonic() < deadline:
            time.sleep(.1)
        assert logins.get(attempt)["status"] == "CANCELLED"
        # Exercise the raw TUI's actual Enter key. With no network and a fake
        # code, the token exchange must fail explicitly instead of waiting forever.
        code_attempt = str(uuid.uuid4())
        logins.start(code_attempt, "antigravity")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            value = logins.get(code_attempt)
            if value.get("input_required") or value["status"] == "ERROR":
                break
            time.sleep(.1)
        assert value["input_required"] is True
        logins.submit(code_attempt, "fixture-invalid-code")
        deadline = time.monotonic() + 15
        while logins.get(code_attempt)["status"] != "ERROR" and time.monotonic() < deadline:
            time.sleep(.1)
        assert logins.get(code_attempt)["status"] == "ERROR"
        checks = run_probe(root)
        checks["official_google_browser_flow_and_exact_auth_cancellation"] = True
        checks["native_code_submission_and_failed_exchange_are_explicit"] = True
    print(json.dumps({"checks": checks, "scope": "Real pinned CLI/Linux sandbox; synthetic OAuth/CodeAssist only; no account access, inference or billing."}, indent=2))


if __name__ == "__main__":
    main()
