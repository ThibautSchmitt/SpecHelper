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
