import json
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from runtime import server


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "test-control-secret")
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(server, "CREDENTIALS", tmp_path / "credentials")
    server.CREDENTIALS.mkdir()
    oauth = server.CREDENTIALS / "codex"
    oauth.mkdir()
    (oauth / "auth.json").write_text(
        json.dumps({"tokens": {"access_token": "synthetic-oauth-fixture"}})
    )
    request_id = str(uuid.uuid4())
    workspace = server.DATA / "analysis-workspaces" / request_id
    workspace.mkdir(parents=True)
    (server.DATA / "requests" / request_id / "attachments").mkdir(parents=True)
    client = TestClient(server.app)
    return (
        client,
        {
            "request_id": request_id,
            "workspace": str(workspace),
            "prompt": "Need",
            "schema": {},
            "timeout": 2,
        },
        tmp_path,
    )


def test_runtime_auth_and_path_confinement(runtime):
    client, payload, _ = runtime
    assert client.post("/run", json=payload).status_code == 401
    response = client.post(
        "/run",
        json={**payload, "workspace": "/etc"},
        headers={"Authorization": "Bearer test-control-secret"},
    )
    assert response.status_code == 422
    assert client.post("/query/unknown", json={"sql": "SELECT 1"}).status_code == 403


def test_runtime_creates_and_resumes_explicit_session(runtime):
    client, payload, root = runtime
    session_id = str(uuid.uuid4())
    commands = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            commands.append(command)
            assert kwargs["env"] == {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}

        def communicate(self, data=None, timeout=None):
            assert data == b"Need"
            session = server.SESSIONS / payload["request_id"]
            (session / "result.json").write_text(json.dumps({"status": "READY_TO_ANALYZE"}))
            return (
                json.dumps({"type": "thread.started", "thread_id": session_id}) + "\n"
            ).encode(), None

    with patch("runtime.server.subprocess.Popen", Process):
        response = client.post(
            "/run",
            json={**payload, "phase": "understanding"},
            headers={"Authorization": "Bearer test-control-secret"},
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == session_id
        response = client.post(
            "/run",
            json={**payload, "session_id": session_id},
            headers={"Authorization": "Bearer test-control-secret"},
        )
        assert response.status_code == 200
    assert "resume" not in commands[0]
    assert commands[1][-3:] == ["resume", session_id, "-"]
    assert 'model_reasoning_effort="low"' in commands[0]
    assert 'model_reasoning_effort="medium"' in commands[1]
    assert commands[0][commands[0].index("--model") + 1] == "gpt-6-luna"
    assert 'sandbox_mode="danger-full-access"' in commands[0]
    assert "--ro-bind" in commands[0]
    assert commands[0][0] == "bwrap"
    assert commands[0][commands[0].index("--cap-drop") + 1] == "ALL"


def test_runtime_kills_agent_on_deadline(runtime):
    client, payload, _ = runtime

    class Process:
        pid = 12345
        calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("codex", 2)
            return b"", None

    with (
        patch("runtime.server.subprocess.Popen", Process),
        patch("runtime.server.os.killpg") as kill,
    ):
        response = client.post(
            "/run", json=payload, headers={"Authorization": "Bearer test-control-secret"}
        )
    assert response.status_code == 200
    assert response.json()["timed_out"] is True
    kill.assert_called_once_with(12345, server.signal.SIGKILL)
    assert not server.capabilities


def test_database_capability_expires_and_is_scoped(runtime):
    client, _, _ = runtime
    server.capabilities["expired"] = {"expires": 0, "config": {}}
    try:
        response = client.post("/query/expired", json={"sql": "SELECT 1"})
        assert response.status_code == 403
    finally:
        server.capabilities.pop("expired")


def test_same_request_independent_contexts_mount_separate_session_roots(runtime):
    client, payload, root = runtime
    mounts = []
    sessions = {}

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            self.session = Path(command[command.index("--bind") + 1])
            mounts.append(self.session)
            sessions.setdefault(self.session, str(uuid.uuid4()))
            self.session.mkdir(parents=True, exist_ok=True)

        def communicate(self, *args, **kwargs):
            (self.session / "result.json").write_text(json.dumps({"fact": "Only this context"}))
            return json.dumps(
                {"type": "thread.started", "thread_id": sessions[self.session]}
            ).encode(), None

    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    with patch("runtime.server.subprocess.Popen", Process):
        for context in (payload["request_id"], first, second, payload["request_id"]):
            response = client.post(
                "/run",
                json={**payload, "context_id": context},
                headers={"Authorization": "Bearer test-control-secret"},
            )
            assert response.status_code == 200
    assert mounts[0] == mounts[3] == server.SESSIONS / payload["request_id"]
    assert len(set(mounts)) == 3
    assert all(
        not a.is_relative_to(b) and not b.is_relative_to(a)
        for a, b in ((mounts[0], mounts[1]), (mounts[0], mounts[2]), (mounts[1], mounts[2]))
    )
