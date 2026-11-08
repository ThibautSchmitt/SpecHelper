"""5/10 distinct synthetic accounts over real HTTP + PostgreSQL, no external writes."""

import json
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from django.db import close_old_connections, connection, connections

from core.models import PublishedTicket, Request, ResultVersion, TicketConnector
from core.secrets import encrypt
from core.ticket_publication import preview, publish

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize("round_number", [1, 2, 3])
@pytest.mark.parametrize("parallel", [5, 10])
def test_account_destination_isolation_and_lost_response_reconciliation(
    environment, parallel, tmp_path, round_number
):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL concurrency")
    state, lock = {}, threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def account(self):
            token = self.headers.get("PRIVATE-TOKEN", "")
            return (
                token.removeprefix("fixture-account-")
                if token.startswith("fixture-account-")
                else ""
            )

        def do_GET(self):
            account = self.account()
            path = urlsplit(self.path).path
            if path == "/api/v4/projects":
                return self.reply(
                    200,
                    [
                        {
                            "id": int(account),
                            "name": "Dedicated account " + account,
                            "path_with_namespace": "test/" + account,
                        }
                    ],
                )
            if not path.startswith("/api/v4/projects/" + account + "/"):
                return self.reply(403, {})
            if path.endswith("/issues"):
                return self.reply(200, state.get(account, []))
            return self.reply(200, [])

        def do_POST(self):
            account = self.account()
            if urlsplit(self.path).path != "/api/v4/projects/" + account + "/issues":
                return self.reply(403, {})
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            # The account, destination, content and source must agree.
            assert data["title"] == "Ticket account " + account
            issue = {
                "id": int(account) * 100,
                "iid": 1,
                "web_url": base + "/test/" + account + "/-/issues/1",
                **data,
            }
            with lock:
                state.setdefault(account, []).append(issue)
            if int(account) % 3 == 0:
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.reply(201, issue)

    class Server(ThreadingHTTPServer):
        request_queue_size = 64

    server = Server(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    operations = []
    for index in range(1, parallel + 1):
        value = Request.objects.create(environment=environment, need="Need account " + str(index))
        version = ResultVersion.objects.create(
            request=value,
            number=1,
            ticket={"title": "Ticket account " + str(index), "need": "Need " + str(index)},
        )
        connector = TicketConnector.objects.create(
            name="Account " + str(index),
            environment=environment,
            platform="gitlab",
            base_url=base,
            secret=encrypt("fixture-account-" + str(index)),
            projects=[str(index)],
            status="CONNECTED",
        )
        connector.environments.add(environment)
        content = preview(version, connector, str(index))
        payload = {
            "project": str(index),
            "title": "Ticket account " + str(index),
            "body": "Need account " + str(index),
            "fields": {},
            "labels": [],
            "assignees": [],
            "template_id": "",
            "issue_type": "",
            "options_revision": content["revision"],
            "idempotency_key": uuid.uuid4(),
            "confirmed": True,
        }
        operations.append((version.pk, connector.pk, payload))
    barrier = threading.Barrier(parallel)

    def execute(operation):
        close_old_connections()
        try:
            version_id, connector_id, payload = operation
            version = ResultVersion.objects.select_related("request__environment").get(
                pk=version_id
            )
            connector = TicketConnector.objects.get(pk=connector_id)
            barrier.wait(20)
            started = time.perf_counter()
            row = publish(version, connector, payload)
            if row.status == "UNCERTAIN":
                row = publish(version, connector, payload)
            assert row.status == "PUBLISHED"
            assert row.connector_id == connector_id and row.version_id == version_id
            assert row.project == payload["project"] and row.external_id == str(
                int(payload["project"]) * 100
            )
            # Repeated confirmation must only read the existing operation.
            assert publish(version, connector, payload).pk == row.pk
            return time.perf_counter() - started
        finally:
            connections.close_all()

    try:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            latencies = list(pool.map(execute, operations))
        assert PublishedTicket.objects.filter(status="PUBLISHED").count() == parallel
        assert set(state) == {str(index) for index in range(1, parallel + 1)}
        assert all(len(rows) == 1 for rows in state.values())
        report = {
            "kind": "controlled-HTTP/PostgreSQL fixture",
            "accounts": parallel,
            "confirmed": parallel,
            "duplicates": 0,
            "isolation_errors": 0,
            "seconds": latencies,
        }
        (tmp_path / f"publication-load-{parallel}.json").write_text(json.dumps(report))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
