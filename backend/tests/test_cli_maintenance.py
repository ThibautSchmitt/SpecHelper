"""Explicit CLI updates preserve running work and the previous executable."""

import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone
from fastapi.testclient import TestClient

from core import cli_maintenance as maintenance
from core.models import CLITool, ConnectionAttempt, InstanceSettings, Job
from core.worker import claim_job
from runtime import cli_maintenance as service
from runtime import cli_tools


@pytest.fixture
def isolated_service(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "TOOLS", tmp_path)
    monkeypatch.setattr(cli_tools, "TOOLS", tmp_path)
    token = tmp_path / "token"
    token.write_text("private-test-token")
    monkeypatch.setattr(service, "TOKEN_FILE", token)
    monkeypatch.setattr(service, "OPERATIONS", {})
    monkeypatch.setattr(service, "installed_versions", lambda: {key: "1.0.0" for key in service.COMMANDS})
    return TestClient(service.app), {"Authorization": "Bearer private-test-token"}, tmp_path


def test_service_requires_private_token_and_rejects_arbitrary_commands(isolated_service):
    client, headers, _ = isolated_service
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=headers).status_code == 200
    for payload in [
        {"agent": "shell", "version": "1.0.0"},
        {"agent": "codex", "version": "../../escape"},
        {"agent": "codex", "version": "1.0.0", "command": "echo secret"},
    ]:
        assert client.post("/install", headers=headers, json={"operation_id": str(uuid.uuid4()), **payload}).status_code == 422


def test_stage_activate_persist_and_rollback_are_separate(isolated_service, monkeypatch):
    client, headers, root = isolated_service
    destination = root / "codex/releases/2.0.0"
    destination.mkdir(parents=True)
    monkeypatch.setattr(service, "install", lambda payload: {"agent": payload.agent, "installed_version": payload.version, "previous": ""})
    key = str(uuid.uuid4())
    staged = client.post("/install", headers=headers, json={"agent": "codex", "version": "2.0.0", "operation_id": key})
    assert staged.json()["status"] == "STAGED"
    active = root / "codex/current"
    assert not active.exists()
    assert client.post("/activate/" + key, headers=headers).json()["status"] == "ACTIVE"
    assert active.resolve() == destination
    service.OPERATIONS.clear()
    assert client.get("/operations/" + key, headers=headers).json()["status"] == "ACTIVE"
    assert client.post("/rollback/" + key, headers=headers).status_code == 200
    assert not active.is_symlink()
    assert client.post("/rollback/" + key, headers=headers).status_code == 200


def test_rollback_cannot_replace_a_newer_activation(isolated_service, monkeypatch):
    client, headers, root = isolated_service
    for version in ("2.0.0", "3.0.0"):
        (root / "codex/releases" / version).mkdir(parents=True)
    monkeypatch.setattr(service, "install", lambda payload: {"agent": payload.agent, "installed_version": payload.version, "previous": ""})
    key = str(uuid.uuid4())
    client.post("/install", headers=headers, json={"agent": "codex", "version": "2.0.0", "operation_id": key})
    client.post("/activate/" + key, headers=headers)
    active = root / "codex/current"
    active.unlink()
    active.symlink_to(root / "codex/releases/3.0.0")
    assert client.post("/rollback/" + key, headers=headers).status_code == 409
    assert active.resolve().name == "3.0.0"


def test_failed_install_preserves_active_release(isolated_service, monkeypatch):
    client, headers, root = isolated_service
    old = root / "codex/releases/1.0.0"
    old.mkdir(parents=True)
    active = root / "codex/current"
    active.symlink_to(old)
    monkeypatch.setattr(service, "install", Mock(side_effect=ValueError("sensitive response")))
    response = client.post("/install", headers=headers, json={"agent": "codex", "version": "2.0.0", "operation_id": str(uuid.uuid4())})
    assert response.status_code == 502
    assert "sensitive" not in response.text
    assert active.resolve() == old


def test_recovery_handles_journal_written_before_symlink_activation(isolated_service):
    client, headers, _ = isolated_service
    key = str(uuid.uuid4())
    service.save_operation(key, {"status": "ACTIVE", "agent": "codex", "installed_version": "2.0.0", "previous": ""})
    assert client.post("/rollback/" + key, headers=headers).json()["status"] == "ROLLED_BACK"


def test_failed_inventory_keeps_last_known_version(isolated_service, monkeypatch):
    _, _, root = isolated_service
    import json
    (root / "release-cache.json").write_text(json.dumps({"checked": 0, "items": {"codex": {"latest_version": "2.0.0"}}}))
    monkeypatch.setattr(service, "release", Mock(side_effect=ValueError("offline")))
    result = service.inventory()
    codex = next(row for row in result["items"] if row["agent"] == "codex")
    assert codex["latest_version"] == "2.0.0" and codex["state"] == "unavailable"


@pytest.mark.django_db
@pytest.mark.parametrize("agent", maintenance.AGENTS)
def test_update_is_explicit_idempotent_and_absent_from_activity(client, settings, agent):
    settings.CLI_MAINTENANCE_URL = "http://maintenance"
    CLITool.objects.create(agent=agent, installed_version="1.0.0", latest_version="2.0.0")
    assert client.get("/api/cli-tools").status_code == 200
    assert not Job.objects.exists()
    response = client.post(f"/api/cli-tools/{agent}/update")
    assert response.status_code == 200
    first = response.json()
    assert first["update_status"] == "QUEUED"
    assert client.post(f"/api/cli-tools/{agent}/update").status_code == 200
    assert Job.objects.count() == 1
    assert client.get("/api/queue").json() == []
    other = next(value for value in maintenance.AGENTS if value != agent)
    assert client.post(f"/api/cli-tools/{other}/update").status_code == 409
    assert client.post("/api/cli-tools/shell/update").status_code == 422


@pytest.mark.django_db
def test_maintenance_waits_for_running_work_then_precedes_queued_work():
    running = Job.objects.create(kind="sync", target="1", status="RUNNING")
    Job.objects.create(kind="sync", target="2")
    update = Job.objects.create(kind="cli_update", target="codex")
    assert claim_job() is None
    running.status = "DONE"
    running.save()
    assert claim_job().pk == update.pk
    assert claim_job() is None


@pytest.mark.django_db
def test_maintenance_waits_for_sign_in_but_ignores_expired_attempts():
    attempt = ConnectionAttempt.objects.create(provider="codex", status="AWAITING_USER", expires_at=timezone.now() + timedelta(minutes=5))
    update = Job.objects.create(kind="cli_update", target="codex")
    assert claim_job() is None
    attempt.expires_at = timezone.now() - timedelta(seconds=1)
    attempt.save()
    assert claim_job().pk == update.pk


@pytest.mark.django_db
def test_refresh_retains_known_versions_when_metadata_fails(monkeypatch, settings):
    settings.CLI_MAINTENANCE_URL = "http://maintenance"
    CLITool.objects.create(agent="codex", installed_version="1.0.0", latest_version="2.0.0")
    monkeypatch.setattr(maintenance, "runtime_call", lambda *args, **kwargs: {"versions": {"codex": "1.1.0"}})
    monkeypatch.setattr(maintenance, "service_call", Mock(side_effect=ValueError("offline")))
    maintenance.refresh_inventory_if_due()
    tool = CLITool.objects.get(agent="codex")
    assert (tool.installed_version, tool.latest_version, tool.check_error) == ("1.1.0", "2.0.0", True)


@pytest.mark.django_db
def test_failed_activation_verification_rolls_back(monkeypatch):
    InstanceSettings.objects.get_or_create(pk=1)
    CLITool.objects.create(agent="codex", installed_version="1.0.0")
    job = Job.objects.create(kind="cli_update", target="codex", status="RUNNING", payload={"version": "2.0.0", "operation_id": str(uuid.uuid4())})
    calls = []
    def call(path, *args, **kwargs):
        calls.append(path)
        return {"status": "STAGED" if path == "/install" else "ACTIVE"}
    monkeypatch.setattr(maintenance, "service_call", call)
    monkeypatch.setattr(maintenance, "runtime_call", lambda *args, **kwargs: {"versions": {"codex": "1.0.0"}})
    with pytest.raises(ValueError, match="previous version was restored"):
        maintenance.perform_update(job)
    assert calls[-1].startswith("/rollback/")
    assert CLITool.objects.get(agent="codex").installed_version == "1.0.0"


@pytest.mark.django_db
def test_orphaned_active_update_is_rolled_back(monkeypatch):
    CLITool.objects.create(agent="codex", installed_version="2.0.0")
    job = Job.objects.create(kind="cli_update", target="codex", status="RUNNING", started_at=timezone.now() - timedelta(minutes=5), payload={"version": "2.0.0", "operation_id": str(uuid.uuid4())})
    calls = []
    def call(path, *args, **kwargs):
        calls.append(path)
        return {"status": "ACTIVE", "activated_at": 1}
    monkeypatch.setattr(maintenance, "_recovery_checked", 0)
    monkeypatch.setattr(maintenance, "service_call", call)
    monkeypatch.setattr(maintenance, "runtime_call", lambda *args, **kwargs: {"versions": {"codex": "1.0.0"}})
    maintenance.recover_updates()
    job.refresh_from_db()
    assert job.status == "ERROR" and calls[-1].startswith("/rollback/")
    assert CLITool.objects.get(agent="codex").installed_version == "1.0.0"


@pytest.mark.django_db
def test_unreachable_maintenance_preserves_admission_gate(monkeypatch):
    job = Job.objects.create(kind="cli_update", target="codex", status="RUNNING", started_at=timezone.now() - timedelta(minutes=5), payload={"version": "2.0.0", "operation_id": str(uuid.uuid4())})
    monkeypatch.setattr(maintenance, "_recovery_checked", 0)
    monkeypatch.setattr(maintenance, "service_call", Mock(side_effect=ValueError("offline")))
    maintenance.recover_updates()
    job.refresh_from_db()
    assert job.status == "RUNNING"
    assert claim_job() is None


@pytest.mark.django_db
def test_successful_update_confirms_actual_version(monkeypatch):
    InstanceSettings.objects.get_or_create(pk=1)
    CLITool.objects.create(agent="codex", installed_version="1.0.0")
    job = Job.objects.create(kind="cli_update", target="codex", status="RUNNING", payload={"version": "2.0.0", "operation_id": str(uuid.uuid4())})
    calls = []
    def call(path, *args, **kwargs):
        calls.append(path)
        return {"status": "STAGED" if path == "/install" else "ACTIVE" if path.startswith("/activate/") else "DONE"}
    monkeypatch.setattr(maintenance, "service_call", call)
    monkeypatch.setattr(maintenance, "runtime_call", lambda *args, **kwargs: {"versions": {"codex": "2.0.0"}})
    maintenance.perform_update(job)
    job.refresh_from_db()
    assert job.status == "DONE" and calls[-1].startswith("/confirm/")
    assert CLITool.objects.get(agent="codex").installed_version == "2.0.0"


@pytest.mark.django_db
def test_supervisor_retains_gate_after_uncertain_process_exit(monkeypatch):
    from core import step_supervisor
    job = Job.objects.create(kind="cli_update", target="codex", status="RUNNING")
    process = Mock()
    process.poll.return_value = 0
    monkeypatch.setattr(step_supervisor, "PROCESSES", {job.pk: (process, None, 0)})
    step_supervisor.poll_processes()
    job.refresh_from_db()
    assert job.status == "RUNNING"
    assert not step_supervisor.PROCESSES
