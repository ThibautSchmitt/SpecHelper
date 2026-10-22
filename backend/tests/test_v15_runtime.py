"""Role contexts must not inherit the legacy primary session directory."""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from runtime import server
from runtime.auth import identity_root


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_independent_roles_have_separate_mounts_history_and_credential_refresh(
    tmp_path, monkeypatch, provider
):
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(server, "CREDENTIALS", tmp_path / "credentials")
    request_id, identity, other_identity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    workspace = server.DATA / "analysis-workspaces" / str(request_id)
    workspace.mkdir(parents=True)
    (server.DATA / "requests" / str(request_id) / "attachments").mkdir(parents=True)
    filename = "auth.json" if provider == "codex" else ".credentials.json"

    def credential(token):
        return (
            {"tokens": {"access_token": token, "account_id": "synthetic-stable-account"}}
            if provider == "codex"
            else {"claudeAiOauth": {"accessToken": token}}
        )

    for account in (identity, other_identity, None):
        directory = identity_root(server.CREDENTIALS, account) / provider
        directory.mkdir(parents=True)
        (directory / filename).write_text(json.dumps(credential("synthetic-original")))
    legacy = server.SESSIONS / str(request_id)
    legacy.mkdir(parents=True)
    (legacy / "analyst-private").write_text("Legacy conversation must not be mounted")
    contexts = [request_id, uuid.uuid4(), uuid.uuid4()]
    observed = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            self.session = Path(command[command.index("--bind") + 1])
            assert self.session == server.SESSIONS / "contexts" / str(request_id) / str(
                contexts[len(observed)]
            )
            assert not (self.session / "analyst-private").exists()
            assert not (self.session / "conversation-id").exists()
            assert "--fork-session" not in command and "--resume" not in command
            assert "resume" not in command
            observed.append(self.session)
            self.sid = str(uuid.uuid4())
            (self.session / "conversation-id").write_text(self.sid)
            (self.session / provider / filename).write_text(
                json.dumps(credential("synthetic-refreshed"))
            )

        def communicate(self, *args, **kwargs):
            (self.session / "result.json").write_text('{"ok":true}')
            value = (
                {"type": "thread.started", "thread_id": self.sid}
                if provider == "codex"
                else {"session_id": self.sid, "structured_output": {"ok": True}}
            )
            return json.dumps(value).encode(), None

    sessions = []
    with patch("runtime.server.subprocess.Popen", Process):
        for context in contexts:
            result = server.run(
                server.RunIn.model_validate(
                    {
                        "request_id": str(request_id),
                        "context_id": str(context),
                        "independent_context": True,
                        "identity_id": str(identity),
                        "agent": provider,
                        "workspace": str(workspace),
                        "prompt": "Read the same immutable source without sharing role notes.",
                        "schema": {},
                        "timeout": 2,
                    }
                )
            )
            assert result["output"] == {"ok": True}
            sessions.append(result["session_id"])
    assert len(set(sessions)) == 3
    assert len(set(observed)) == 3
    for account in (other_identity, None):
        value = json.loads(
            (identity_root(server.CREDENTIALS, account) / provider / filename).read_text()
        )
        assert value == credential("synthetic-original")
    assert json.loads(
        (identity_root(server.CREDENTIALS, identity) / provider / filename).read_text()
    ) == credential("synthetic-refreshed")


def test_independent_default_context_and_legacy_context_remain_distinct(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(server, "CREDENTIALS", tmp_path / "credentials")
    request_id = uuid.uuid4()
    workspace = server.DATA / "analysis-workspaces" / str(request_id)
    workspace.mkdir(parents=True)
    payload = {
        "request_id": str(request_id),
        "workspace": str(workspace),
        "prompt": "Read only",
        "schema": {},
        "timeout": 2,
    }
    # Missing credentials stop execution after directory selection, without a CLI call.
    for independent in (False, True):
        assert server.run(
            server.RunIn.model_validate({**payload, "independent_context": independent})
        ) == {
            "failure": {"kind": "AUTH_ERROR"},
            "context_usage": [],
            "context_audit": "unavailable",
        }
    assert (server.SESSIONS / str(request_id) / "codex").is_dir()
    assert (server.SESSIONS / "contexts" / str(request_id) / str(request_id) / "codex").is_dir()
