"""Authenticated control relay; keeps the agent network away from the application API."""

import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from django.conf import settings

from .agent import runtime_call


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self):
        token = settings.RUNTIME_TOKEN
        if not token or not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + token
        ):
            self.respond(401, {"detail": "Access denied"})
            return
        parsed = urlsplit(self.path)
        health = parsed.path == "/health" and self.command == "GET"
        auth_get = bool(re.fullmatch(r"/auth/[a-f0-9-]{36}", parsed.path)) and self.command == "GET"
        auth_post = (
            bool(re.fullmatch(r"/auth/(?:start|[a-f0-9-]{36}/(?:code|cancel))", parsed.path))
            and self.command == "POST"
        )
        if not (health or auth_get or auth_post):
            self.respond(404, {"detail": "Commande indisponible"})
            return
        target = parsed.path
        if health:
            agent = parse_qs(parsed.query).get("agent", ["codex"])[0]
            if agent not in {"codex", "claude"}:
                self.respond(422, {"detail": "Unknown assistant"})
                return
            target += "?agent=" + agent
        try:
            payload = None
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 8192:
                    self.respond(413, {"detail": "Request too large"})
                    return
                payload = json.loads(self.rfile.read(length) or b"{}")
            self.respond(200, runtime_call(target, payload))
        except ValueError:
            self.respond(502, {"detail": "Connection service unavailable"})

    do_GET = dispatch
    do_POST = dispatch


def start_gateway(host="0.0.0.0", port=8091):
    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="runtime-control").start()
    return server
