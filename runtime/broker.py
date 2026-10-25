"""Per-run provider broker: real credentials and destination selection stay outside the sandbox."""

import contextlib
import hashlib
import http.client
import json
import logging
import os
import re
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


def read_chunked_body(stream):
    """Decode only bounded HTTP chunks; extensions and trailers are unsupported."""
    body = bytearray()
    for _ in range(1024):
        line = stream.readline(128)
        if not re.fullmatch(rb"[0-9a-fA-F]{1,8}\r\n", line):
            raise ValueError("Invalid chunk framing")
        size = int(line[:-2], 16)
        if not size:
            if stream.readline(128) != b"\r\n":
                raise ValueError("Unexpected trailers")
            return bytes(body)
        if len(body) + size > MAX_BODY:
            raise ValueError("Body limit exceeded")
        chunk = stream.read(size)
        if len(chunk) != size or stream.read(2) != b"\r\n":
            raise ValueError("Truncated chunk")
        body.extend(chunk)
    raise ValueError("Too many chunks")


class Broker:
    def __init__(self, provider, credentials, timeout, database=None, web=False):
        self.provider = provider
        self.credentials = credentials
        self.deadline = time.monotonic() + timeout
        self.database = database
        self.database_checks = []
        self.database_lock = threading.Lock()
        from .web_sources import WebReader

        self.web = WebReader(timeout, self.redact) if web else None
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
        elif self.provider == "antigravity":
            if self.credentials.get("auth_mode") == "google_oauth":
                # Preserve the native personal-account protocol. The child may
                # select a read/inference method, never a host or account token.
                allowed = {
                    "loadCodeAssist", "fetchAvailableModels", "listExperiments", "fetchUserInfo",
                    "streamGenerateContent", "generateContent", "countTokens",
                }
                prefix = "/antigravity-oauth/v1internal:"
                if (
                    method == "POST" and parsed.path.startswith(prefix)
                    and parsed.path.removeprefix(prefix) in allowed
                    and parsed.query in {"", "alt=sse"}
                ):
                    return "https://daily-cloudcode-pa.googleapis.com" + path.removeprefix(
                        "/antigravity-oauth"
                    )
                return None
            # The official explicit Gemini API mode supports a custom base URL.
            # No OAuth profile or caller-chosen endpoint is forwarded.
            match = re.fullmatch(
                r"/antigravity/v1beta/models/([A-Za-z0-9._-]{1,100}):"
                r"(generateContent|streamGenerateContent|countTokens)", parsed.path
            )
            if method == "POST" and match and parsed.query in {"", "alt=sse"}:
                return "https://generativelanguage.googleapis.com" + path.removeprefix("/antigravity")
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
        elif self.provider == "claude":
            headers["Authorization"] = "Bearer " + self.credentials["claudeAiOauth"]["accessToken"]
        elif self.provider == "antigravity":
            if self.credentials.get("auth_mode") == "google_oauth":
                headers["Authorization"] = "Bearer " + self.credentials["credential"]["token"]["access_token"]
            else:
                headers["x-goog-api-key"] = self.credentials["api_key"]
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
                transfer = self.headers.get("Transfer-Encoding")
                chunked = (
                    transfer == "chunked" and broker.provider == "antigravity"
                    and broker.credentials.get("auth_mode") == "google_oauth"
                    and not self.headers.get_all("Content-Length")
                    and len(self.headers.get_all("Transfer-Encoding", [])) == 1
                )
                if (transfer and not chunked) or not 0 <= length <= MAX_BODY:
                    broker.audit("network_denied")
                    return self.reply(413, {"error": "Provider request exceeds limits"})
                try:
                    body = read_chunked_body(self.rfile) if chunked else self.rfile.read(length)
                except (ValueError, OSError):
                    broker.audit("network_denied")
                    return self.reply(413, {"error": "Provider request exceeds limits"})
                if self.command == "POST" and self.path in {"/web", "/web/search"}:
                    if not broker.web:
                        broker.audit("network_denied")
                        return self.reply(
                            403, {"error": "Web references are unavailable in this step"}
                        )
                    try:
                        payload = json.loads(body)
                        key = "query" if self.path == "/web/search" else "url"
                        if set(payload) != {key} or not isinstance(payload[key], str):
                            raise ValueError("Invalid reference request")
                        result = (
                            broker.web.search(payload[key])
                            if key == "query"
                            else broker.web.read(payload[key])
                        )
                        return self.reply(200, result)
                    except (
                        ValueError,
                        TypeError,
                        OSError,
                        TimeoutError,
                        http.client.HTTPException,
                    ):
                        broker.audit("web_reference_denied_or_unavailable")
                        return self.reply(
                            422,
                            {"error": "Public HTTPS reference denied, unavailable or over budget"},
                        )
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
                authenticated = secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + broker.token
                )
                if (
                    broker.provider == "antigravity"
                    and broker.credentials.get("auth_mode") != "google_oauth"
                ):
                    authenticated = secrets.compare_digest(
                        self.headers.get("x-goog-api-key", ""), broker.token
                    )
                if not target or not authenticated:
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
        if self.provider == "antigravity":
            secret = self.credentials.get("api_key", "")
            if isinstance(secret, str) and len(secret) >= 8:
                encoded = encoded.replace(secret, "[REDACTED]")
            for name in ("access_token", "refresh_token", "id_token"):
                secret = self.credentials.get("credential", {}).get("token", {}).get(name, "")
                if isinstance(secret, str) and len(secret) >= 8:
                    encoded = encoded.replace(secret, "[REDACTED]")
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
