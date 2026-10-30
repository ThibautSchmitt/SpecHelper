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
    monkeypatch.setattr(server, "connection_status", lambda *a, **kw: {"quota_status": {"state": "unavailable"}})
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
        response = client.post("/run", json={**payload, "model": "native-model", "reasoning_effort": "high"}, headers={"Authorization": "Bearer test-control-secret"})
        assert response.status_code == 200
    assert commands[2][commands[2].index("--model")+1] == "native-model"
    assert 'model_reasoning_effort="high"' in commands[2]
    assert "resume" not in commands[0]
    assert commands[1][-3:] == ["resume", session_id, "-"]
    assert not any("model_reasoning_effort=" in part for command in commands[:2] for part in command)
    assert "--model" not in commands[0]
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


@pytest.mark.parametrize("provider", ["codex", "claude", "antigravity"])
def test_persistent_conversation_resumes_in_its_own_readonly_context(runtime, monkeypatch, provider):
    client, payload, _ = runtime
    credentials = server.CREDENTIALS / provider
    credentials.mkdir(exist_ok=True)
    if provider == "claude":
        (credentials / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "synthetic-oauth-fixture"}}))
    elif provider == "antigravity":
        (credentials / "auth.json").write_text(json.dumps({"auth_mode": "gemini_api_key", "api_key": "synthetic-key", "billing_confirmed": True}))
        monkeypatch.setattr("runtime.server.subscription_credentials", lambda *a: True)
        monkeypatch.setattr("runtime.model_discovery.discover", lambda *a: {"state": "supported", "items": [{"identifier": "fixture-model"}]})
    commands, mounts = [], []
    native_id, context_id = str(uuid.uuid4()), str(uuid.uuid4())

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            commands.append(command)
            self.session = Path(command[command.index("--bind") + 1])
            mounts.append(self.session)
            assert "--ro-bind" in command and "--cap-drop" in command
            assert self.session != server.SESSIONS / payload["request_id"]

        def communicate(self, *args, **kwargs):
            output = {"message": "Scoped reply"}
            if provider == "claude":
                return json.dumps({"structured_output": output, "session_id": native_id}).encode(), None
            if provider == "antigravity":
                events = [{"event": "init", "conversation_id": native_id, "init": {"permission_mode": "request-review", "model": "fixture-model", "tools": []}}, {"event": "result", "result": {"conversation_id": native_id, "status": "SUCCESS", "structured_output": output}}]
                return ("\n".join(json.dumps(e) for e in events) + "\n").encode(), None
            (self.session / "result.json").write_text(json.dumps(output))
            return json.dumps({"type": "thread.started", "thread_id": native_id}).encode(), None

    with patch("runtime.server.subprocess.Popen", Process):
        for native in (None, native_id):
            response = client.post("/run", json={**payload, "agent": provider, "model": "fixture-model", "persistent_conversation": True, "independent_context": True, "context_id": context_id, "session_id": native}, headers={"Authorization": "Bearer test-control-secret"})
            assert response.status_code == 200, response.text
            assert response.json().get("session_id") == native_id, response.text
    assert mounts[0] == mounts[1]
    flag = {"codex": "resume", "claude": "--resume", "antigravity": "--conversation"}[provider]
    assert flag not in commands[0]
    assert commands[1][commands[1].index(flag) + 1] == native_id


@pytest.mark.parametrize("text", [b"session not found", b"No conversation found with session ID", b"failed to load rollout"])
def test_explicit_missing_session_is_distinct_from_quota_or_transport_failure(text):
    assert server.session_unavailable(b"", text)
    assert not server.session_unavailable(b"RESOURCE_EXHAUSTED")
    assert not server.session_unavailable(b"connection reset by peer")


def test_missing_codex_session_error_is_recoverable_without_raw_diagnostics(runtime):
    client, payload, _ = runtime

    class Process:
        returncode = 1

        def __init__(self, command, **kwargs):
            kwargs["stderr"].write(b"failed to load rollout: private-session-details")

        def communicate(self, *args, **kwargs):
            return b"", None

    with patch("runtime.server.subprocess.Popen", Process):
        response = client.post("/run", json={**payload, "persistent_conversation": True,
            "session_id": str(uuid.uuid4())}, headers={"Authorization": "Bearer test-control-secret"})
    assert response.status_code == 200
    assert response.json()["failure"]["kind"] == "SESSION_UNAVAILABLE"
    assert "private-session-details" not in response.text


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_streamed_runtime_reads_real_captured_events_and_keeps_final_contract(runtime, provider):
    client, payload, _ = runtime
    native_id = str(uuid.uuid4())
    credentials = server.CREDENTIALS / provider
    credentials.mkdir(exist_ok=True)
    if provider == "claude":
        (credentials / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "synthetic-oauth-fixture"}}))
    commands = []

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            commands.append(command)
            self.stream = kwargs["stdout"]
            self.session = Path(command[command.index("--bind") + 1])

        def communicate(self, *args, **kwargs):
            answer = {"message": "A scoped answer"}
            if provider == "claude":
                events = [
                    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "read-1", "name": "Read", "input": {"file_path": "/private/source"}}]}},
                    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "read-1", "content": "PRIVATE SOURCE"}]}},
                    {"type": "result", "structured_output": answer, "session_id": native_id},
                ]
            else:
                (self.session / "result.json").write_text(json.dumps(answer))
                events = [
                    {"type": "thread.started", "thread_id": native_id},
                    {"type": "item.completed", "item": {"id": "read-1", "type": "command_execution", "command": "cat /private/source", "exit_code": 0, "aggregated_output": "PRIVATE SOURCE"}},
                    {"type": "item.completed", "item": {"id": "reply", "type": "agent_message", "text": json.dumps(answer)}},
                ]
            self.stream.write(("\n".join(json.dumps(event) for event in events) + "\n").encode())
            self.stream.flush()
            return None, None

    with patch("runtime.server.subprocess.Popen", Process):
        response = client.post("/run", json={**payload, "agent": provider, "attempt_id": str(uuid.uuid4()), "stream_events": True, "preview_field": "message"}, headers={"Authorization": "Bearer test-control-secret"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    frames = [json.loads(line) for line in response.text.splitlines()]
    assert frames[-1]["type"] == "result"
    assert frames[-1]["result"]["output"] == {"message": "A scoped answer"}
    assert frames[-1]["result"]["session_id"] == native_id
    progress = [frame for frame in frames if frame["type"] == "progress"]
    assert progress and progress[-1]["events"][-1]["state"] == "done"
    assert progress[-1]["events"][-1]["operation"] == "read"
    assert "PRIVATE SOURCE" not in json.dumps(progress) and "/private/source" not in json.dumps(progress)
    if provider == "claude":
        assert commands[0][commands[0].index("--output-format") + 1] == "stream-json"
        assert "--include-partial-messages" in commands[0]


def test_streaming_requires_an_exact_execution_attempt(runtime):
    client, payload, _ = runtime
    response = client.post("/run", json={**payload, "stream_events": True}, headers={"Authorization": "Bearer test-control-secret"})
    assert response.status_code == 422
