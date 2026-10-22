"""Real HTTP integration against a controlled GitLab-compatible contract fixture."""

import json
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from core.models import Request, TicketConnector
from core.results import publish
from core.secrets import encrypt

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("lose_response", [False, True])
def test_confirmed_http_creation_and_lost_response_reconciliation(
    client, environment, bundle, monkeypatch, lose_response
):
    state = {"issues": [], "posts": 0, "authorized": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data):
            encoded = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def authorize(self):
            if self.headers.get("PRIVATE-TOKEN") != "fixture-only-ticket-token":
                self.reply(401, {"message": "Unauthorized"})
                return False
            state["authorized"] += 1
            return True

        def do_GET(self):
            if not self.authorize():
                return
            path = urlsplit(self.path).path
            if path == "/api/v4/projects":
                self.reply(200, [{"id": 7, "name": "Target", "path_with_namespace": "team/target"}])
            elif path == "/api/v4/projects/7/issues":
                self.reply(200, state["issues"])
            elif path in {
                "/api/v4/projects/7/templates/issues",
                "/api/v4/projects/7/labels",
                "/api/v4/projects/7/members/all",
            }:
                self.reply(200, [])
            else:
                self.reply(404, {})

        def do_POST(self):
            if not self.authorize():
                return
            if urlsplit(self.path).path != "/api/v4/projects/7/issues":
                self.reply(404, {})
                return
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["posts"] += 1
            issue = {"id": 901, "iid": 12, "web_url": base + "/team/target/-/issues/12", **data}
            state["issues"].append(issue)
            if lose_response:
                # The server accepted the write, but the client never sees its response.
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.reply(201, issue)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    try:
        request = Request.objects.create(environment=environment, need="Export contracts")
        version = publish(request.pk, None, bundle)
        connector = TicketConnector.objects.create(
            name="Controlled HTTP fixture",
            platform="gitlab",
            base_url=base,
            secret=encrypt("fixture-only-ticket-token"),
            projects=["7"],
            status="CONNECTED",
        )
        endpoint = f"/api/requests/{request.pk}/versions/{version.number}"
        prepared = client.post(
            endpoint + "/publication-preview",
            data=json.dumps({"connector_id": connector.pk, "project": "7"}),
            content_type="application/json",
        )
        assert prepared.status_code == 200
        preview = prepared.json()
        payload = {
            "connector_id": connector.pk,
            "project": "7",
            "title": preview["title"],
            "body": preview["body"],
            "fields": {},
            "labels": [],
            "assignees": [],
            "template_id": "",
            "issue_type": "",
            "options_revision": preview["revision"],
            "idempotency_key": str(uuid.uuid4()),
            "confirmed": False,
        }
        denied = client.post(
            endpoint + "/publications", data=json.dumps(payload), content_type="application/json"
        )
        assert denied.status_code == 422 and state["posts"] == 0
        payload["confirmed"] = True
        response = client.post(
            endpoint + "/publications", data=json.dumps(payload), content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json()["status"] == ("UNCERTAIN" if lose_response else "PUBLISHED")
        repeated = client.post(
            endpoint + "/publications", data=json.dumps(payload), content_type="application/json"
        )
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "PUBLISHED"
        assert repeated.json()["external_id"] == "901"
        assert state["posts"] == 1
        assert state["authorized"] > 1
        assert len(client.get("/api/tickets").json()["items"]) == 1
        assert version.artifacts.get(name="ticket.md").content == preview["body"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
