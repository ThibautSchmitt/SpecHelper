"""Provider usage refresh never sends a model prompt or erases known limits."""

import io
import json
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.models import AIConnection, AIIdentity
from core.providers import mark_failure, observe, public, record_quota
from runtime.auth import connection_status, quota_status
from runtime.quota import app_server_windows, read_codex_quota


def test_app_server_quota_uses_observed_durations_only():
    assert app_server_windows(
        {
            "rateLimits": {
                "primary": {"windowDurationMins": 300, "usedPercent": 27, "resetsAt": 2000000000},
                "secondary": {"windowDurationMins": 10080, "usedPercent": 100},
            }
        }
    ) == {
        "session": {
            "used_percent": 27,
            "exhausted": False,
            "resets_at": "2033-05-18T03:33:20+00:00",
        },
        "weekly": {"used_percent": 100, "exhausted": True},
    }
    assert app_server_windows({"rateLimits": {"primary": {"usedPercent": 10}}}) == {}


def test_app_server_exchange_has_only_initialization_and_usage_read(tmp_path):
    class Stream(io.StringIO):
        def close(self):
            pass

    class Process:
        def __init__(self, command, **kwargs):
            assert command == ["codex", "app-server", "--stdio"]
            self.stdin = Stream()
            self.stdout = io.StringIO(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {"id": 1, "result": {}},
                        {"method": "notification"},
                        {"id": 2, "result": {"rateLimits": {}}},
                    ]
                )
                + "\n"
            )

        def poll(self):
            return 0

        def wait(self, **kwargs):
            pass

    process = Process(["codex", "app-server", "--stdio"])
    with patch("runtime.quota.subprocess.Popen", return_value=process):
        assert read_codex_quota(tmp_path, {}) == {"rateLimits": {}}
    calls = [json.loads(line) for line in process.stdin.getvalue().splitlines()]
    assert [call["method"] for call in calls] == [
        "initialize",
        "initialized",
        "account/rateLimits/read",
    ]


def test_codex_refresh_uses_clean_home_and_excludes_inherited_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-ignored")
    directory = tmp_path / "codex"
    directory.mkdir()
    (directory / "auth.json").write_text(
        json.dumps({"tokens": {"account_id": "test-account", "access_token": "synthetic-oauth"}})
    )
    (directory / "config.toml").write_text("untrusted config")

    def read(home, env):
        assert home != directory
        assert sorted(path.name for path in home.iterdir()) == ["auth.json"]
        assert "OPENAI_API_KEY" not in env
        return {
            "accountId": "test-account",
            "rateLimits": {"primary": {"windowDurationMins": 300, "usedPercent": 43}},
        }

    with patch("runtime.auth.read_codex_quota", side_effect=read):
        value = quota_status(tmp_path, directory, "codex", "CONNECTED")
    assert value["quota_status"]["state"] == "available"
    assert value["quota_windows"]["session"]["used_percent"] == 43
    assert not value["ordinary_usage_allowed"]


@pytest.mark.parametrize(
    "agent,status,reason",
    [("claude", "CONNECTED", "unsupported_cli"), ("codex", "DISCONNECTED", "not_connected")],
)
def test_unavailable_quota_never_probes_with_a_prompt(tmp_path, agent, status, reason):
    with patch("runtime.auth.read_codex_quota") as read:
        value = quota_status(tmp_path, tmp_path, agent, status)
    assert value["quota_status"]["state"] == "unavailable"
    assert value["quota_status"]["reason"] == reason
    read.assert_not_called()


def test_disconnected_refresh_reports_unavailable_without_starting_cli(tmp_path):
    with patch("runtime.auth.subprocess.run") as run:
        value = connection_status(tmp_path, "codex", include_quota=True)
    assert value["quota_status"]["reason"] == "not_connected"
    run.assert_not_called()


def test_provider_error_is_sanitized_and_cross_account_snapshot_is_rejected(tmp_path):
    directory = tmp_path / "codex"
    directory.mkdir()
    (directory / "auth.json").write_text(json.dumps({"tokens": {"account_id": "expected"}}))
    for result in [
        ValueError("synthetic-private-provider-error"),
        {"accountId": "wrong", "rateLimits": {}},
    ]:
        with patch(
            "runtime.auth.read_codex_quota",
            side_effect=result if isinstance(result, Exception) else None,
            return_value=result,
        ):
            value = quota_status(tmp_path, directory, "codex", "CONNECTED")
        assert value["quota_status"]["reason"] == "refresh_failed"
        assert value["quota_status"]["state"] == "error"
        assert "private" not in json.dumps(value)


@pytest.mark.django_db
def test_error_keeps_last_known_quota_and_exhaustion(client):
    identity = AIIdentity.objects.create(
        agent="codex",
        status="CONNECTED",
        availability="QUOTA_EXHAUSTED",
        quota_windows={
            "weekly": {
                "used_percent": 100,
                "exhausted": True,
                "observed_at": timezone.now().isoformat(),
            }
        },
    )
    connection = AIConnection.objects.create(
        agent="codex", identity=identity, status="CONNECTED", availability="QUOTA_EXHAUSTED"
    )
    with patch(
        "core.ai_api.runtime_call",
        return_value={
            "status": "CONNECTED",
            "quota_status": {"state": "error", "reason": "refresh_failed", "private": "discard"},
        },
    ) as caller:
        response = client.post(f"/api/ai-connections/{connection.pk}/test")
    assert response.status_code == 200
    assert "quota=true" in caller.call_args.args[0]
    assert response.json()["quota_windows"]["weekly"]["used_percent"] == 100
    assert response.json()["availability"] == "QUOTA_EXHAUSTED"
    assert response.json()["quota_status"]["reason"] == "refresh_failed"
    assert "private" not in response.json()["quota_status"]


@pytest.mark.django_db
def test_fresh_quota_shared_without_inferring_recovery():
    identity = AIIdentity.objects.create(
        agent="codex", status="CONNECTED", availability="QUOTA_EXHAUSTED"
    )
    connection = AIConnection.objects.create(
        agent="codex", identity=identity, status="CONNECTED", availability="QUOTA_EXHAUSTED"
    )
    other = AIConnection.objects.create(agent="codex", identity=identity)
    result = observe(
        connection,
        {
            "status": "CONNECTED",
            "quota_status": {"state": "available", "reason": ""},
            "quota_windows": {"session": {"used_percent": 10}},
        },
    )
    assert result["availability"] == "QUOTA_EXHAUSTED"
    assert public(other)["quota_windows"]["session"]["used_percent"] == 10
    assert public(other)["quota_status"]["state"] == "available"
    assert (
        observe(
            connection,
            {
                "status": "CONNECTED",
                "quota_status": {"state": "available", "reason": ""},
                "ordinary_usage_allowed": True,
            },
        )["availability"]
        == "AVAILABLE"
    )


@pytest.mark.django_db
def test_analysis_observation_and_failure_preserve_refresh_metadata():
    identity = AIIdentity.objects.create(agent="codex", status="CONNECTED")
    connection = AIConnection.objects.create(agent="codex", identity=identity, status="CONNECTED")
    observe(
        connection,
        {"status": "CONNECTED", "quota_status": {"state": "unavailable", "reason": "not_reported"}},
    )
    record_quota(connection, {"session": {"used_percent": 20}})
    metadata = public(connection)["quota_status"]
    assert metadata["state"] == "unavailable"
    mark_failure(connection.pk, "QUOTA_EXHAUSTED")
    connection.refresh_from_db()
    assert public(connection)["quota_status"] == metadata
    assert public(connection)["quota_windows"]["session"]["used_percent"] == 20
