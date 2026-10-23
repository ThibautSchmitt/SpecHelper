"""Real TLS/session/CSRF exercise against the fixed disposable frontend, without host ports."""

import http.client
import http.cookiejar
import json
import ssl
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ORIGIN = "https://localhost:8443"
POLICY = "default-src 'none'"


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def dispatch(self):
        connection = http.client.HTTPConnection("frontend", 3000, timeout=10)
        try:
            headers = {
                key: value for key, value in self.headers.items()
                if key.lower() in {"cookie", "content-type", "origin", "x-csrftoken"}
            }
            headers.update(Host="localhost:8443")
            headers["X-Forwarded-Host"] = "localhost:8443"
            headers["X-Forwarded-Proto"] = "https"
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            connection.request(self.command, self.path, body=body, headers=headers)
            result = connection.getresponse()
            data = result.read(2 * 1024 * 1024)
            self.send_response(result.status)
            for name, value in result.getheaders():
                if name.lower() not in {"content-length", "transfer-encoding", "connection"}:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            connection.close()

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch


def exercise(certificate):
    jar = http.cookiejar.CookieJar()
    context = ssl.create_default_context(cafile=str(certificate))
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), urllib.request.HTTPCookieProcessor(jar)
    )

    def request(path, method="GET", data=None, csrf=None, origin=ORIGIN, cookie=None):
        headers = {"Origin": origin}
        if cookie:
            headers["Cookie"] = cookie
        if data is not None:
            headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRFToken"] = csrf
        req = urllib.request.Request(
            ORIGIN + path, method=method, headers=headers,
            data=json.dumps(data).encode() if data is not None else None,
        )
        try:
            response = opener.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            value = json.loads(body) if body and "json" in response.headers.get("Content-Type", "") else None
            return response.status, value, response.headers

    assert request("/api/settings")[0] == 401, "Anonymous settings access was not denied"
    assert request("/api/requests/00000000-0000-4000-8000-000000000000")[0] == 401
    status, session, headers = request("/api/access/session")
    assert status == 200 and session["mode"] == "password" and not session["authenticated"]
    csrf_cookie = next(cookie for cookie in jar if cookie.name == "spechelper_csrf")
    assert csrf_cookie.secure and csrf_cookie.has_nonstandard_attr("HttpOnly")
    assert csrf_cookie.get_nonstandard_attr("SameSite") == "Strict"
    password = Path("/auth/access-password").read_text().strip()
    assert request("/api/access/login", "POST", {"password": password})[0] == 403
    status, authenticated, headers = request("/api/access/login", "POST", {"password": password}, session["csrf_token"])
    assert status == 200 and authenticated["authenticated"] and authenticated["expires_at"]
    assert authenticated["csrf_token"] != session["csrf_token"]
    access_cookie = next(cookie for cookie in jar if cookie.name == "spechelper_session")
    assert access_cookie.secure and access_cookie.has_nonstandard_attr("HttpOnly")
    assert access_cookie.get_nonstandard_attr("SameSite") == "Strict"
    old_session = "spechelper_session=" + access_cookie.value
    status, settings, headers = request("/api/settings")
    assert status == 200 and POLICY in headers.get("Content-Security-Policy", "")
    assert request("/api/settings", "PUT", {**settings, "name": "Forbidden mutation"}, authenticated["csrf_token"], "https://evil.invalid")[0] == 403
    assert request("/api/settings")[1] == settings
    assert request("/api/access/logout", "POST", {})[0] == 403
    assert request("/api/access/logout", "POST", {}, authenticated["csrf_token"])[0] == 200
    assert request("/api/settings")[0] == 401
    assert request("/api/settings", cookie=old_session)[0] == 401
    try:
        urllib.request.urlopen("http://frontend:3000/api/access/session", timeout=10)
    except urllib.error.HTTPError as error:
        assert error.code in {403, 503}
    else:
        raise AssertionError("Cleartext authentication was not refused")
    return {
        "tls_certificate_verified": True, "anonymous_admin_denied": True,
        "secure_httponly_samesite_cookies": True, "csrf_required": True,
        "login_rotates_csrf": True, "hostile_origin_rejected": True,
        "logout_revokes_access": True, "cleartext_auth_refused": True,
    }


def main():
    with tempfile.TemporaryDirectory(prefix="spechelper-tls-") as temporary:
        root = Path(temporary)
        certificate, key = root / "certificate.pem", root / "private.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
            "-keyout", str(key), "-out", str(certificate),
        ], check=True, capture_output=True, timeout=15)
        key.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        with ThreadingHTTPServer(("127.0.0.1", 8443), Proxy) as server:
            server.socket = context.wrap_socket(server.socket, server_side=True)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                result = exercise(certificate)
            finally:
                server.shutdown()
        print(json.dumps(result))


if __name__ == "__main__":
    main()
