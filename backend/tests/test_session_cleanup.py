import json
import uuid

import pytest
from fastapi.testclient import TestClient

from runtime import server
from runtime.session_cleanup import release


def test_release_only_owned_contexts_and_fences_delayed_requests(tmp_path):
    request, context, other = [str(uuid.uuid4()) for _ in range(3)]
    parent = tmp_path / "contexts" / request
    own = parent / context
    random_home = parent / str(uuid.uuid4())
    preserved = parent / other
    for home in [own, random_home, preserved]:
        home.mkdir(parents=True)
        (home / "state").write_text("native resumable state")
    (random_home / ".spechelper-context").write_text(json.dumps({"context": context}))
    assert release(tmp_path, request, [context])
    assert not own.exists() and not random_home.exists()
    assert preserved.exists() and (parent / (".retired-" + context)).exists()
    assert release(tmp_path, request, [context])


def test_symlink_and_path_escape_are_refused(tmp_path):
    request, context = [str(uuid.uuid4()) for _ in range(2)]
    outside = tmp_path / "credentials"
    outside.mkdir()
    (outside / "keep").write_text("secret fixture")
    parent = tmp_path / "contexts" / request
    parent.mkdir(parents=True)
    (parent / context).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        release(tmp_path, request, [context])
    with pytest.raises(ValueError):
        release(tmp_path, request, ["../../credentials"])
    assert (outside / "keep").exists()


def test_release_requires_authentication_and_waits_for_active_invocation(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_TOKEN", "cleanup-control")
    monkeypatch.setattr(server, "SESSIONS", tmp_path)
    request, context, attempt = [str(uuid.uuid4()) for _ in range(3)]
    monkeypatch.setattr(server, "run_controls", {(request, attempt): {"active": True}})
    payload = {"request_id": request, "context_ids": [context]}
    client = TestClient(server.app)
    assert client.post("/sessions/release", json=payload).status_code == 401
    headers = {"Authorization": "Bearer cleanup-control"}
    assert client.post("/sessions/release", json=payload, headers=headers).json() == {
        "released": False
    }
    server.run_controls[(request, attempt)]["active"] = False
    assert client.post("/sessions/release", json=payload, headers=headers).json() == {
        "released": True
    }
    assert (
        client.post(
            "/sessions/release", json={**payload, "path": "/credentials"}, headers=headers
        ).status_code
        == 422
    )


def test_native_budget_queues_without_starting_another_process(tmp_path, monkeypatch):
    request = uuid.uuid4()
    workspace = tmp_path / "analysis-workspaces" / str(request)
    workspace.mkdir(parents=True)
    monkeypatch.setattr(server, "DATA", tmp_path)
    monkeypatch.setattr(server, "validated_resources", lambda *args: [])
    monkeypatch.setattr(
        server, "locks", {("other-one", "job"): object(), ("other-two", "job"): object()}
    )
    monkeypatch.setattr(server, "run_controls", {})
    result = server.execute_run(
        server.RunIn(
            request_id=request,
            attempt_id=uuid.uuid4(),
            workspace=str(workspace),
            prompt="Fixture",
            schema={},
            timeout=2,
        )
    )
    assert result == {"failure": {"kind": "BUSY", "retry_seconds": 5}}
    assert len(server.locks) == 2
