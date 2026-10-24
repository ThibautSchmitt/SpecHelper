"""Per-run provider broker: real credentials and destination selection stay outside the sandbox."""

import contextlib
import hashlib
import json
import logging
import os
import secrets
import socketserver
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi.encoders import jsonable_encoder

LOG = logging.getLogger("spechelper.runtime.security")
MAX_BODY = 2 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024


class Broker:
    def __init__(self, provider, credentials, timeout, database=None):
        self.provider = provider
        self.credentials = credentials
        self.deadline = time.monotonic() + timeout
        self.database = database
        self.database_checks = []
        self.database_lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.events = {"network_denied": 0, "credential_read_attempt": 0}
        self.temporary = None
        self.server = None
        self.thread = None

    def audit(self, kind):
        self.events[kind] = min(self.events.get(kind, 0) + 1, 10000)
        LOG.warning("runtime_security_event kind=%s", kind)

    def query_database(self, sql):
        """Attach a service-authored receipt; no result rows or credentials enter history."""
        from core.postgres import audit_sql, validate_query

        receipt = {
            "query_id": "sql-"
            + uuid.uuid4().hex
            + "-"
            + hashlib.sha256(sql.encode()).hexdigest()[:12],
            "sql": "",
            "checked_at": datetime.now(UTC).isoformat(),
            "status": "rejected",
            "row_count": 0,
            "rows_exposed": 0,
            "truncated": False,
        }
        with self.database_lock:
            if len(self.database_checks) >= 100:
                raise ValueError("Query budget exhausted")
            self.database_checks.append(receipt)
        try:
            validate_query(sql)
            receipt["sql"] = audit_sql(sql)
            receipt["status"] = "unavailable"
            value = self.database(sql)
            receipt.update(
                status="checked",
                row_count=min(value.get("observed_row_count", len(value.get("rows", []))), 201),
                rows_exposed=min(len(value.get("rows", [])), 200),
                truncated=bool(value.get("truncated")),
            )
            return {**value, "query_id": receipt["query_id"], "checked_at": receipt["checked_at"]}
        except (ValueError, TypeError):
            raise ValueError("Read-only query rejected or unavailable") from None

    def destination(self, method, path):
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.fragment or "%" in parsed.path:
            return None
        if self.provider == "codex":
            allowed = {
                ("POST", "/codex/responses"),
                ("POST", "/codex/responses/compact"),
                ("GET", "/codex/models"),
            }
            if (method, parsed.path) in allowed:
                return "https://chatgpt.com/backend-api" + path
        elif self.provider == "claude":
            allowed = {
                ("POST", "/claude/v1/messages"),
                ("POST", "/claude/v1/messages/count_tokens"),
            }
            if (method, parsed.path) in allowed:
                return "https://api.anthropic.com" + path.removeprefix("/claude")
        return None

    def headers(self, incoming):
        allowed = {
            "content-type",
            "accept",
            "anthropic-version",
            "anthropic-beta",
            "user-agent",
            "originator",
            "session_id",
            "x-client-request-id",
        }
        headers = {key: value for key, value in incoming.items() if key.lower() in allowed}
        if self.provider == "codex":
            tokens = self.credentials["tokens"]
            headers["Authorization"] = "Bearer " + tokens["access_token"]
            if tokens.get("account_id"):
                headers["ChatGPT-Account-Id"] = tokens["account_id"]
        else:
            headers["Authorization"] = "Bearer " + self.credentials["claudeAiOauth"]["accessToken"]
        return headers

    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="spechelper-broker-")
        directory = Path(self.temporary.name)
        directory.chmod(0o711)
        self.path = directory / "provider.sock"
        broker = self

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True
            request_queue_size = 16
            slots = threading.BoundedSemaphore(16)

            def process_request(self, request, client_address):
                if not self.slots.acquire(blocking=False):
                    broker.audit("network_denied")
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, client_address)
                except BaseException:
                    self.slots.release()
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self.slots.release()

            def handle_error(self, request, client_address):
                broker.audit("broker_request_failed")

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                self.request.settimeout(min(10, max(1, broker.deadline - time.monotonic())))
                super().setup()

            def log_message(self, *args):
                pass

            def reply(self, status, body):
                encoded = json.dumps(jsonable_encoder(body)).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(encoded)
                self.close_connection = True

            def dispatch(self):
                if time.monotonic() >= broker.deadline:
                    return self.reply(403, {"error": "Provider capability expired"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    return self.reply(400, {"error": "Invalid request size"})
                if self.headers.get("Transfer-Encoding") or not 0 <= length <= MAX_BODY:
                    broker.audit("network_denied")
                    return self.reply(413, {"error": "Provider request exceeds limits"})
                body = self.rfile.read(length)
                if self.command == "POST" and self.path == "/database" and broker.database:
                    try:
                        payload = json.loads(body)
                        if (
                            set(payload) != {"sql"}
                            or not isinstance(payload["sql"], str)
                            or len(payload["sql"]) > 20000
                        ):
                            raise ValueError("Invalid query")
                        return self.reply(200, broker.query_database(payload["sql"]))
                    except (ValueError, TypeError):
                        return self.reply(422, {"error": "Read-only query rejected"})
                target = broker.destination(self.command, self.path)
                if not target or not secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + broker.token
                ):
                    broker.audit("network_denied")
                    return self.reply(403, {"error": "Destination or credential denied"})
                try:
                    # Never inherit environment proxies, forward client auth or follow redirects.
                    with httpx.Client(
                        timeout=httpx.Timeout(min(20, max(1, broker.deadline - time.monotonic()))),
                        trust_env=False,
                        follow_redirects=False,
                    ) as client:
                        with client.stream(
                            self.command, target, content=body, headers=broker.headers(self.headers)
                        ) as response:
                            if response.is_redirect:
                                broker.audit("network_denied")
                                return self.reply(502, {"error": "Provider redirect denied"})
                            self.send_response(response.status_code)
                            self.send_header(
                                "Content-Type",
                                response.headers.get("Content-Type", "application/json"),
                            )
                            for name, value in response.headers.items():
                                if (
                                    name.lower().startswith(
                                        ("x-codex-", "x-ratelimit-", "anthropic-ratelimit-")
                                    )
                                    and len(value) <= 256
                                ):
                                    self.send_header(name, value)
                            self.send_header("Connection", "close")
                            self.end_headers()
                            size = 0
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > MAX_RESPONSE or time.monotonic() >= broker.deadline:
                                    broker.audit("network_denied")
                                    break
                                self.wfile.write(chunk)
                                self.wfile.flush()
                            self.close_connection = True
                except (httpx.HTTPError, OSError):
                    with contextlib.suppress(OSError):
                        self.reply(502, {"error": "Provider unavailable"})

            do_GET = dispatch
            do_POST = dispatch
            do_CONNECT = dispatch
            do_PUT = dispatch
            do_DELETE = dispatch

        self.server = Server(str(self.path), Handler)
        os.chmod(self.path, 0o600)
        if os.geteuid() == 0:
            os.chown(self.path, 10001, 10001)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.temporary:
            self.temporary.cleanup()

    def observe_commands(self, stdout):
        # The CLI event stream is untrusted: record fixed categories, never command text.
        text = stdout.decode(errors="replace") if isinstance(stdout, bytes) else str(stdout)
        sensitive = (
            "/credentials",
            "/control",
            "refresh_token",
            ".credentials.json",
            "auth.json",
            "/proc/1/environ",
            "docker.sock",
        )
        if any(term in text for term in sensitive):
            self.audit("credential_read_attempt")
        if any(
            term in text
            for term in (
                "curl http",
                "wget http",
                "socket.connect",
                "urllib.request",
                "requests.get(",
            )
        ):
            self.audit("network_attempt")

    def observe_session(self, session):
        for index, path in enumerate(session.rglob("*.jsonl")):
            if index >= 16:
                break
            if path.is_symlink() or not path.is_file():
                continue
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 2 * 1024 * 1024))
                self.observe_commands(stream.read(2 * 1024 * 1024))

    def redact(self, value):
        encoded = json.dumps(value)
        for section in ("tokens", "claudeAiOauth"):
            for key, secret in self.credentials.get(section, {}).items():
                if (
                    key
                    in {"access_token", "refresh_token", "id_token", "accessToken", "refreshToken"}
                    and isinstance(secret, str)
                    and len(secret) >= 8
                ):
                    encoded = encoded.replace(secret, "[REDACTED]")
        return json.loads(encoded)
