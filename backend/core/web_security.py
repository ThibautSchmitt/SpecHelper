"""Authentication and accounting at the shared instance boundary, never per-user tenancy."""

import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token, rotate_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .security_models import AccessSession, SecurityBucket, SecurityEvent

SAFE = {"GET", "HEAD", "OPTIONS"}
ACCESS_PATHS = {"/api/access/session", "/api/access/login", "/api/access/logout"}
RESOURCES = {
    "requests",
    "questions",
    "settings",
    "connections",
    "ai-connections",
    "git-connections",
    "environments",
    "ticket-connectors",
    "tickets",
    "orchestration-settings",
    "databases",
    "system",
    "agents",
    "skills",
    "library",
    "library-assistant",
    "ai-models",
    "queue",
    "access",
    "health",
    "docs",
    "openapi.json",
}


def fingerprint(value):
    return hmac.new(settings.SECRET_KEY.encode(), str(value).encode(), hashlib.sha256).hexdigest()


def password_material():
    """A file stays outside the application database; invalid or missing files fail closed."""
    encoded = settings.ACCESS_PASSWORD_HASH
    filename = settings.ACCESS_PASSWORD_FILE
    if filename:
        try:
            path = Path(filename)
            if path.is_symlink() or path.stat().st_mode & 0o077:
                return "invalid", ""
            encoded = path.read_text().strip()
            if not 16 <= len(encoded) <= 4096:
                return "invalid", ""
        except (OSError, UnicodeError):
            return "invalid", ""
    if not encoded:
        return "none", ""
    is_hash = encoded.startswith(("pbkdf2_", "argon2$", "scrypt$", "bcrypt"))
    if not filename and not is_hash:
        return "invalid", ""
    return ("hash" if is_hash else "plain"), encoded


def loopback_host(value):
    try:
        if ipaddress.ip_address(value).is_loopback:
            return True
    except (ValueError, TypeError):
        pass
    try:
        parsed = urlsplit("//" + value)
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return False
        host = parsed.hostname
        return host in {"localhost", "testserver"} or ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def access_mode(request):
    kind, _ = password_material()
    if kind != "none":
        return "password" if kind != "invalid" else "unconfigured"
    if not settings.ACCESS_LOCAL_ONLY or not loopback_host(settings.ACCESS_BIND_ADDRESS):
        return "unconfigured"
    if not all(loopback_host(urlsplit(origin).netloc) for origin in settings.TRUSTED_ORIGINS):
        return "unconfigured"
    host = request.get_host()
    # Docker's private backend hostname is allowed only behind the loopback-bound frontend.
    if not loopback_host(host) and host.split(":", 1)[0] != "backend":
        return "unconfigured"
    forwarded = request.headers.get("X-Forwarded-Host")
    if forwarded and not loopback_host(forwarded):
        return "unconfigured"
    return "local"


def authenticated_session(request):
    value = request.COOKIES.get(settings.ACCESS_COOKIE_NAME, "")
    if not isinstance(value, str) or len(value) != 64:
        return None
    _, material = password_material()
    session = AccessSession.objects.filter(
        token_hash=fingerprint(value),
        expires_at__gt=timezone.now(),
        credential_version=fingerprint(material),
    ).first()
    return session


def csrf_valid(request):
    # Ninja marks its routes csrf_exempt; apply Django's protection explicitly at this boundary.
    rejection = CsrfViewMiddleware(lambda request: None).process_view(
        request, lambda request: None, (), {}
    )
    return rejection is None


def public_response(value, status=200):
    response = JsonResponse(value, status=status)
    response["Cache-Control"] = "no-store, private"
    response["Vary"] = "Cookie"
    return response


def actor_key(request):
    session = getattr(request, "access_session", None)
    return (
        session.token_hash if session else fingerprint(request.META.get("REMOTE_ADDR", "unknown"))
    )


def audit(request, action, status):
    """Never record body, query, headers, raw identifiers, addresses or exception text."""
    resource = request.path.split("/")[2:3]
    name = resource[0] if resource and resource[0] in RESOURCES else "other"
    SecurityEvent.objects.create(
        actor=actor_key(request), action=action, resource=name, status=status
    )
    cutoff = timezone.now() - timedelta(days=settings.SECURITY_AUDIT_RETENTION_DAYS)
    SecurityEvent.objects.filter(created_at__lt=cutoff).delete()
    AccessSession.objects.filter(expires_at__lte=timezone.now()).delete()
    SecurityBucket.objects.filter(updated_at__lt=timezone.now() - timedelta(days=1)).delete()


def acquire(request, category="api"):
    """Serialize accounting in the database so multiple API processes share limits."""
    key = fingerprint(actor_key(request) + category)
    now = time.time()
    interval = int(now // 60)
    limit = (
        settings.ACCESS_LOGIN_RATE
        if category == "login"
        else settings.ACCESS_READ_RATE
        if request.method in SAFE
        else settings.ACCESS_WRITE_RATE
    )
    capacity = settings.ACCESS_CONCURRENCY
    lease = secrets.token_hex(16)
    with transaction.atomic():
        SecurityBucket.objects.get_or_create(key=key)
        bucket = SecurityBucket.objects.select_for_update().get(pk=key)
        count = bucket.count if bucket.window == interval else 0
        active = {
            token: expiry
            for token, expiry in bucket.leases.items()
            if isinstance(expiry, (int, float)) and expiry > now
        }
        if count >= limit or len(active) >= capacity:
            return None
        active[lease] = now + settings.ACCESS_LEASE_SECONDS
        bucket.window, bucket.count, bucket.leases = interval, count + 1, active
        bucket.save(update_fields=["window", "count", "leases", "updated_at"])
    return key, lease


def release(handle):
    if handle is None:
        return
    key, lease = handle
    with transaction.atomic():
        bucket = SecurityBucket.objects.select_for_update().filter(pk=key).first()
        if bucket:
            bucket.leases.pop(lease, None)
            bucket.save(update_fields=["leases", "updated_at"])


def login_body(request):
    try:
        if int(request.META.get("CONTENT_LENGTH", "0")) > 8192:
            return None
        value = json.loads(request.body)
        password = value.get("password") if isinstance(value, dict) else None
        if not isinstance(password, str) or not 1 <= len(password) <= 4096:
            return None
        return password
    except (ValueError, UnicodeError):
        return None


@require_http_methods(["GET"])
def session_view(request):
    mode = access_mode(request)
    session = authenticated_session(request) if mode == "password" else None
    return public_response(
        {
            "mode": mode,
            "authenticated": mode == "local" or session is not None,
            "csrf_token": get_token(request),
            "expires_at": session.expires_at.isoformat() if session else None,
        },
        status=503 if mode == "unconfigured" else 200,
    )


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    if access_mode(request) != "password":
        return public_response({"detail": "Instance access is not configured."}, 503)
    if not csrf_valid(request):
        audit(request, "csrf_denied", 403)
        return public_response({"detail": "Request verification failed. Reload and retry."}, 403)
    handle = acquire(request, "login")
    if handle is None:
        audit(request, "login_limited", 429)
        response = public_response({"detail": "Too many attempts. Try again shortly."}, 429)
        response["Retry-After"] = "60"
        return response
    try:
        password = login_body(request)
        kind, material = password_material()
        valid = password is not None and (
            check_password(password, material)
            if kind == "hash"
            else hmac.compare_digest(password.encode(), material.encode())
            if kind == "plain"
            else False
        )
        if not valid:
            audit(request, "login_denied", 401)
            return public_response({"detail": "Authentication failed."}, 401)
        old = request.COOKIES.get(settings.ACCESS_COOKIE_NAME, "")
        AccessSession.objects.filter(token_hash=fingerprint(old)).delete()
        token = secrets.token_hex(32)
        expires = timezone.now() + timedelta(seconds=settings.ACCESS_SESSION_SECONDS)
        session = AccessSession.objects.create(
            token_hash=fingerprint(token),
            credential_version=fingerprint(material),
            expires_at=expires,
        )
        request.access_session = session
        rotate_token(request)
        response = public_response(
            {
                "authenticated": True,
                "mode": "password",
                "csrf_token": get_token(request),
                "expires_at": expires.isoformat(),
            }
        )
        response.set_cookie(
            settings.ACCESS_COOKIE_NAME,
            token,
            max_age=settings.ACCESS_SESSION_SECONDS,
            httponly=True,
            secure=request.is_secure() or settings.ACCESS_REQUIRE_HTTPS,
            samesite="Strict",
            path="/",
        )
        audit(request, "login", 200)
        return response
    finally:
        release(handle)


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    if access_mode(request) == "password" and not csrf_valid(request):
        return public_response({"detail": "Request verification failed. Reload and retry."}, 403)
    token = request.COOKIES.get(settings.ACCESS_COOKIE_NAME, "")
    AccessSession.objects.filter(token_hash=fingerprint(token)).delete()
    rotate_token(request)
    response = public_response({"authenticated": False, "csrf_token": get_token(request)})
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/", samesite="Strict")
    audit(request, "logout", 200)
    return response
