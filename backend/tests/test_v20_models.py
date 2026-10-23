import io
import json
import uuid
from pathlib import Path

import pytest

from core.model_catalog import (
    ModelIn,
    add_model,
    list_catalog,
    record_execution,
    refresh,
    validate_model,
)
from core.models import AIConnection, AIIdentity, AIModel, AIModelObservation
from runtime import model_discovery


@pytest.mark.django_db
def test_models_are_never_fabricated_and_legacy_identifiers_remain_unverified():
    assert list_catalog()["items"] == []
    connection = AIConnection.objects.create(agent="claude", model="explicit-legacy-model")
    catalog = list_catalog(connection=connection)
    assert catalog["items"][0]["identifier"] == "explicit-legacy-model"
    assert catalog["items"][0]["status"] == "UNKNOWN"
    assert catalog["items"][0]["source"] == "configured"
    assert catalog["discovery"]["state"] == "unknown"


@pytest.mark.django_db
def test_new_model_selection_requires_an_enabled_matching_provider_entry():
    from ninja.errors import HttpError

    validate_model("codex", "")
    with pytest.raises(HttpError):
        validate_model("codex", "invented")
    item = add_model(
        None,
        ModelIn(agent="claude", identifier="admin-choice", name="Admin choice", family="family-a"),
    )
    validate_model("claude", "admin-choice")
    with pytest.raises(HttpError):
        validate_model("codex", "admin-choice")
    AIModel.objects.filter(pk=item["id"]).update(enabled=False)
    with pytest.raises(HttpError):
        validate_model("claude", "admin-choice")


@pytest.mark.django_db
def test_model_discovery_is_identity_scoped_and_not_entitlement(monkeypatch):
    connection = AIConnection.objects.create(
        agent="codex", identity=AIIdentity.objects.create(agent="codex", credential_id=uuid.uuid4())
    )
    another = AIConnection.objects.create(
        agent="codex", identity=AIIdentity.objects.create(agent="codex", credential_id=uuid.uuid4())
    )
    monkeypatch.setattr(
        "core.model_catalog.runtime_call",
        lambda *args, **kwargs: {
            "state": "supported",
            "reason": "catalog_not_entitlement",
            "items": [{"identifier": "catalog-model", "name": "Catalog model"}],
        },
    )
    value = refresh(connection)
    assert value["discovery"]["state"] == "supported"
    assert value["items"][0]["status"] == "SUPPORTED"
    assert value["items"][0]["reason"] == "catalog_not_entitlement"
    assert list_catalog(connection=another)["items"][0]["status"] == "UNKNOWN"
    record_execution(connection, "catalog-model", True)
    actual_observation = AIModelObservation.objects.get(identity=connection.identity)
    assert refresh(connection)["items"][0]["status"] == "AVAILABLE"
    assert (
        AIModelObservation.objects.get(identity=connection.identity).checked_at
        == actual_observation.checked_at
    )
    record_execution(connection, "catalog-model", False)
    assert list_catalog(connection=connection)["items"][0]["status"] == "UNAVAILABLE"
    assert list_catalog(connection=another)["items"][0]["status"] == "UNKNOWN"


@pytest.mark.django_db
def test_unsupported_and_error_discovery_never_invent_or_leak_provider_errors(monkeypatch):
    connection = AIConnection.objects.create(agent="claude")
    monkeypatch.setattr(
        "core.model_catalog.runtime_call",
        lambda *args, **kwargs: {"state": "unavailable", "reason": "unsupported_cli", "items": []},
    )
    result = refresh(connection)
    assert result["items"] == []
    assert result["discovery"]["reason"] == "unsupported_cli"

    def failed(*args, **kwargs):
        raise ValueError("private upstream payload")

    monkeypatch.setattr("core.model_catalog.runtime_call", failed)
    result = refresh(connection)
    assert result["discovery"]["state"] == "error"
    assert "private" not in json.dumps(result, default=str)


@pytest.mark.django_db
def test_missing_catalog_entry_becomes_unknown_without_cross_identity_change(monkeypatch):
    connection = AIConnection.objects.create(agent="codex")
    record_execution(connection, "retired-model", True)
    monkeypatch.setattr(
        "core.model_catalog.runtime_call",
        lambda *args, **kwargs: {
            "state": "supported",
            "reason": "catalog_not_entitlement",
            "items": [],
        },
    )
    value = refresh(connection)
    assert value["items"][0]["status"] == "UNKNOWN"
    assert AIModelObservation.objects.get().reason == "not_in_latest_catalog"


@pytest.mark.django_db
def test_catalog_api_edits_test_status_and_cross_provider_guard(client, monkeypatch):
    response = client.post(
        "/api/ai-models",
        data=json.dumps({"agent": "codex", "identifier": "admin-model", "name": "Admin model"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    model = response.json()
    assert model["status"] == "UNKNOWN" and model["family"] == "openai"
    codex = AIConnection.objects.create(agent="codex")
    claude = AIConnection.objects.create(agent="claude")
    assert client.get(f"/api/ai-models?agent=claude&connection_id={codex.pk}").status_code == 422
    monkeypatch.setattr(
        "core.model_catalog.runtime_call",
        lambda *args, **kwargs: {
            "state": "supported",
            "reason": "catalog_not_entitlement",
            "items": [{"identifier": "admin-model", "name": "Admin model", "agent": "claude"}],
        },
    )
    result = client.post(f"/api/ai-connections/{codex.pk}/models/{model['id']}/test").json()
    assert result["model"]["agent"] == "codex"
    assert result["model"]["status"] == "SUPPORTED"
    assert result["inference_performed"] is False and result["access_verified"] is False
    assert (
        client.post(f"/api/ai-connections/{claude.pk}/models/{model['id']}/test").status_code == 404
    )
    response = client.put(
        f"/api/ai-models/{model['id']}",
        data=json.dumps({"enabled": False, "name": "Renamed"}),
        content_type="application/json",
    )
    assert response.status_code == 200 and response.json()["name"] == "Renamed"
    assert (
        client.post(f"/api/ai-connections/{codex.pk}/models/{model['id']}/test").status_code == 404
    )
    bad = client.post(
        "/api/ai-models",
        data=json.dumps(
            {
                "agent": "copilot",
                "identifier": "unvalidated",
                "name": "Unvalidated",
                "command": "shell",
            }
        ),
        content_type="application/json",
    )
    assert bad.status_code == 422


class Input(io.StringIO):
    def __init__(self):
        super().__init__()
        self.sent = []

    def write(self, value):
        self.sent.append(json.loads(value))
        return super().write(value)


class Process:
    def __init__(self, responses):
        self.stdin = Input()
        self.stdout = io.StringIO("\n".join(json.dumps(item) for item in responses) + "\n")
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True

    def wait(self, **kwargs):
        return 0


def test_codex_discovery_paginates_only_metadata_and_does_not_create_threads(monkeypatch, tmp_path):
    process = Process(
        [
            {"id": 1, "result": {}},
            {
                "id": 2,
                "result": {
                    "data": [{"model": "model-one", "displayName": "Model one"}],
                    "nextCursor": "page2",
                },
            },
            {
                "id": 3,
                "result": {
                    "data": [{"model": "model-hidden", "hidden": True}, {"model": "model-two"}],
                    "nextCursor": None,
                },
            },
        ]
    )
    monkeypatch.setattr(model_discovery.subprocess, "Popen", lambda *args, **kwargs: process)
    result = model_discovery.read_codex_models(tmp_path, {"HOME": str(tmp_path)})
    assert result == [
        {"identifier": "model-one", "name": "Model one"},
        {"identifier": "model-two", "name": "model-two"},
    ]
    assert [item["method"] for item in process.stdin.sent] == [
        "initialize",
        "initialized",
        "model/list",
        "model/list",
    ]
    assert process.stdin.sent[-1]["params"]["cursor"] == "page2"
    assert process.terminated


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"model": "bad\nidentifier"}], "nextCursor": None},
        {"data": "not-list", "nextCursor": None},
        {"data": [], "nextCursor": 123},
    ],
)
def test_codex_discovery_rejects_malformed_metadata_and_cleans_process(
    monkeypatch, tmp_path, payload
):
    process = Process([{"id": 1, "result": {}}, {"id": 2, "result": payload}])
    monkeypatch.setattr(model_discovery.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(ValueError):
        model_discovery.read_codex_models(tmp_path, {})
    assert process.terminated


def test_discovery_materializes_private_credentials_without_billed_key_inheritance(
    monkeypatch, tmp_path
):
    original = b'{"tokens":{"access_token":"fixture-only"}}'
    (tmp_path / "codex").mkdir()
    (tmp_path / "codex/auth.json").write_bytes(b"encrypted-placeholder")
    monkeypatch.setattr(model_discovery, "subscription_credentials", lambda *args: True)
    monkeypatch.setattr(model_discovery, "read_credential", lambda *args: original)
    refreshed = []
    monkeypatch.setattr(model_discovery, "publish_refresh", lambda *args: refreshed.append(args))
    materialized = []

    def read(home, env):
        materialized.append(Path(home))
        assert (home / "auth.json").read_bytes() == original
        assert (home / "auth.json").stat().st_mode & 0o777 == 0o600
        assert home.stat().st_mode & 0o777 == 0o700
        assert set(env) == {"PATH", "HOME", "CODEX_HOME"}
        return [{"identifier": "observed-model", "name": "Observed model"}]

    monkeypatch.setattr(model_discovery, "read_codex_models", read)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    result = model_discovery.discover(tmp_path, "codex")
    assert result["state"] == "supported" and result["access_verified"] is False
    assert refreshed
    assert not materialized[0].exists()


def test_claude_unsupported_discovery_is_explicit_and_never_invokes_an_inference(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(model_discovery, "subscription_credentials", lambda *args: True)

    def forbidden(*args, **kwargs):
        pytest.fail("No CLI inference or model guess is permitted")

    monkeypatch.setattr(model_discovery.subprocess, "Popen", forbidden)
    result = model_discovery.discover(tmp_path, "claude")
    assert result["state"] == "unavailable" and result["reason"] == "unsupported_cli"
    assert result["items"] == []


def test_runtime_model_catalog_requires_control_authentication(monkeypatch):
    from fastapi.testclient import TestClient

    from runtime import server

    monkeypatch.setattr(server, "control_token", lambda: "fixture-control")
    client = TestClient(server.app)
    response = client.get("/models?agent=codex", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized runtime"}
