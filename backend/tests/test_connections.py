import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.models import AIConnection, ConnectionAttempt

pytestmark = pytest.mark.django_db(transaction=True)


def test_github_button_starts_background_browser_login(client):
    with patch("core.connections.subprocess.Popen") as process:
        response = client.post(
            "/api/connections/start",
            data=json.dumps({"provider": "github"}),
            content_type="application/json",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "STARTING"
    assert "connect_github" in process.call_args.args[0]
    assert "token" not in body
    assert client.get(f"/api/connections/attempts/{body['id']}").json()["status"] == "STARTING"
    assert (
        client.post(f"/api/connections/attempts/{body['id']}/cancel").json()["status"]
        == "CANCELLED"
    )


def test_browser_login_completion_keeps_independent_assistants(client):
    state = {
        "status": "AWAITING_USER",
        "verification_uri": "https://claude.ai/oauth/authorize?state=fixture",
        "input_required": True,
        "user_code": "",
        "message": "Connectez-vous",
    }
    with patch("core.connections.runtime_call", return_value=state):
        response = client.post(
            "/api/connections/start",
            data=json.dumps({"provider": "claude"}),
            content_type="application/json",
        )
    body = response.json()
    assert response.status_code == 200
    assert body["input_required"] is True
    with patch("core.api.runtime_call", return_value={**state, "input_required": False}) as runtime:
        assert (
            client.post(
                f"/api/connections/attempts/{body['id']}/code",
                data=json.dumps({"code": "fixture#code"}),
                content_type="application/json",
            ).status_code
            == 200
        )
        assert runtime.call_args.args[1] == {"code": "fixture#code"}
    with patch(
        "core.connections.runtime_call",
        return_value={"status": "CONNECTED", "message": "Connection successful"},
    ):
        assert client.get(f"/api/connections/attempts/{body['id']}").json()["status"] == "CONNECTED"
    assert AIConnection.objects.get(pk=2).agent == "claude"
    assert AIConnection.objects.get(pk=2).status == "CONNECTED"
    assert client.get("/api/connections").json()["ai"]["agent"] == "claude"


def test_pending_login_reused_without_blocking_other_provider(client, environment):
    pending = ConnectionAttempt.objects.create(
        provider="codex", expires_at=timezone.now() + timedelta(minutes=5)
    )
    result = client.post(
        "/api/connections/start",
        data=json.dumps({"provider": "codex"}),
        content_type="application/json",
    )
    assert result.json()["id"] == str(pending.id)
    with patch("core.connections.runtime_call", return_value={"status": "AWAITING_USER"}):
        result = client.post(
            "/api/connections/start",
            data=json.dumps({"provider": "claude"}),
            content_type="application/json",
        )
    assert result.status_code == 200
    assert AIConnection.objects.get(pk=1).status == "CONNECTED"
    AIConnection.objects.filter(pk=1).update(availability="BUSY")
    result = client.post(
        "/api/connections/start",
        data=json.dumps({"provider": "codex"}),
        content_type="application/json",
    )
    assert result.status_code == 409
