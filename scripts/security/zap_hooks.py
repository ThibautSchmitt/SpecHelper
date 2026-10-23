"""Authenticate only to the fixed disposable Compose target; never a supplied URL."""

import http.cookiejar
import json
import os
import urllib.request
from pathlib import Path

TARGET = "http://frontend:3000"


def zap_started(zap, target):
    if target.rstrip("/") != TARGET:
        raise RuntimeError("Security scans may target only the disposable frontend")
    password = Path("/run/secrets/access-password").read_text().strip()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(TARGET + "/api/access/session", timeout=10) as response:
        session = json.load(response)
    token = session["csrf_token"]
    request = urllib.request.Request(
        TARGET + "/api/access/login",
        data=json.dumps({"password": password}).encode(),
        headers={"Content-Type": "application/json", "Origin": TARGET, "X-CSRFToken": token},
    )
    with opener.open(request, timeout=10) as response:
        authenticated = json.load(response)
    if not authenticated.get("authenticated"):
        raise RuntimeError("Disposable scanner authentication did not succeed")
    cookies = "; ".join(cookie.name + "=" + cookie.value for cookie in jar)
    token = authenticated.get("csrf_token", token)
    # Replacement is restricted to the exact disposable origin. Tokens are not printed.
    for description, name, value in (("scan-cookie", "Cookie", cookies), ("scan-csrf", "X-CSRFToken", token), ("scan-origin", "Origin", TARGET)):
        zap.replacer.add_rule(description, True, "REQ_HEADER", False, name, value, url=TARGET + "/.*")
    zap.spider.set_option_max_depth(3)
    zap.spider.set_option_max_children(20)
    zap.ascan.set_option_max_scan_duration_in_mins(4)
    zap.ascan.set_option_max_rule_duration_in_mins(1)
    zap.ascan.set_option_thread_per_host(2)
    # Auth-only endpoints would invalidate the scanner session or brute-force login.
    for path in ("/api/access/logout", "/api/access/login"):
        zap.spider.exclude_from_scan(TARGET + path + ".*")
        zap.ascan.exclude_from_scan(TARGET + path + ".*")
    for path in ("/", "/questions", "/tickets", "/admin", "/api/settings", "/api/environments", "/api/requests", "/api/questions", "/api/queue", "/api/tickets"):
        zap.urlopen(TARGET + path)
    Path("/zap/wrk/authentication.json").write_text(json.dumps({"authenticated": True, "target": TARGET, "mode": os.environ.get("SPECHELPER_DAST_MODE", "baseline")}))
