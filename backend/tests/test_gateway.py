from unittest.mock import patch

import httpx

from core.gateway import start_gateway


def test_control_gateway_requires_secret_and_does_not_expose_application_or_run_routes(settings):
    settings.RUNTIME_TOKEN = "fixture-control-secret"
    server = start_gateway("127.0.0.1", 0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with (
            httpx.Client(timeout=3) as client,
            patch("core.gateway.runtime_call", return_value={"status": "DISCONNECTED"}) as relay,
        ):
            assert client.get(base + "/health").status_code == 401
            assert not relay.called
            headers = {"Authorization": "Bearer fixture-control-secret"}
            assert client.post(base + "/run", json={}, headers=headers).status_code == 404
            assert client.get(base + "/api/settings", headers=headers).status_code == 404
            assert client.get(base + "/health?agent=claude", headers=headers).json() == {
                "status": "DISCONNECTED"
            }
            relay.assert_called_once_with("/health?agent=claude", None)
            assert (
                client.post(
                    base + "/auth/start",
                    json={"provider": "claude", "attempt_id": "fixture"},
                    headers=headers,
                ).status_code
                == 200
            )
            assert relay.call_args.args == (
                "/auth/start",
                {"provider": "claude", "attempt_id": "fixture"},
            )
    finally:
        server.shutdown()
        server.server_close()


def test_gateway_preserves_selected_identity_and_explicit_quota_read(settings):
    settings.RUNTIME_TOKEN = "fixture-control-secret"
    server = start_gateway("127.0.0.1", 0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    identity = "12345678-1234-4234-8234-123456789abc"
    headers = {"Authorization": "Bearer fixture-control-secret"}
    try:
        with httpx.Client(timeout=3) as client, patch("core.gateway.runtime_call", return_value={"quota_status": {"state": "available"}}) as relay:
            path = f"/health?agent=codex&identity_id={identity}&quota=true"
            response = client.get(base + path, headers=headers)
            assert response.json() == {"quota_status": {"state": "available"}}
            relay.assert_called_once_with(path, None, timeout=25)
            for query in ("identity_id=../other", "quota=run", "quota=true&quota=false", "identity_id=&quota=true"):
                relay.reset_mock()
                assert client.get(base + "/health?agent=codex&" + query, headers=headers).status_code == 422
                relay.assert_not_called()
            relay.reset_mock()
            path = f"/health?agent=claude&identity_id={identity}"
            assert client.get(base + path, headers=headers).status_code == 200
            relay.assert_called_once_with(path, None)
    finally:
        server.shutdown()
        server.server_close()
