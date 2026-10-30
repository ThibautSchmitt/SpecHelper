"""Host, origin, authentication, CSRF and request budgets for the shared API."""

import re
import uuid
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.deprecation import MiddlewareMixin

from .web_security import (
    ACCESS_PATHS,
    SAFE,
    access_mode,
    acquire,
    audit,
    authenticated_session,
    csrf_valid,
    public_response,
    release,
)


class SecureCsrfMiddleware(CsrfViewMiddleware):
    def process_response(self, request, response):
        response = super().process_response(request, response)
        if request.is_secure() and settings.CSRF_COOKIE_NAME in response.cookies:
            response.cookies[settings.CSRF_COOKIE_NAME]["secure"] = True
        return response


class SameOriginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.get_host()
        if request.method not in SAFE:
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                return JsonResponse({"detail": "Origin denied"}, status=403)
            allowed = {*settings.TRUSTED_ORIGINS, f"{request.scheme}://{request.get_host()}"}
            if origin:
                try:
                    parsed = urlsplit(origin)
                except ValueError:
                    return JsonResponse({"detail": "Origin denied"}, status=403)
                if (
                    parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                    or origin not in allowed
                ):
                    return JsonResponse({"detail": "Origin denied"}, status=403)
        return self.get_response(request)


class AccessMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not request.path.startswith("/api/"):
            return None
        # Health reveals no business data; Compose must be able to check it before migrations.
        if request.path == "/api/health" and request.method in {"GET", "HEAD"}:
            return None
        from .discussion_access import identify

        identify(request)
        length = request.META.get("CONTENT_LENGTH")
        try:
            if length and (int(length) < 0 or int(length) > settings.ACCESS_MAX_REQUEST_BYTES):
                return public_response({"detail": "Request too large."}, 413)
        except ValueError:
            return public_response({"detail": "Invalid request length."}, 400)
        mode = access_mode(request)
        request.access_mode = mode
        request.access_session = authenticated_session(request) if mode == "password" else None
        if mode == "password" and settings.ACCESS_REQUIRE_HTTPS and not request.is_secure():
            return public_response({"detail": "HTTPS is required for authenticated access."}, 403)
        if mode == "unconfigured" and request.path != "/api/access/session":
            return public_response(
                {"detail": "Configure authenticated access before exposing this instance."}, 503
            )
        if request.path in ACCESS_PATHS:
            return None
        if mode == "password" and request.access_session is None:
            handle = acquire(request, "anonymous")
            if handle is None:
                response = public_response({"detail": "Too many requests. Try again shortly."}, 429)
                response["Retry-After"] = "60"
                return response
            release(handle)
            audit(request, "access_denied", 401)
            return public_response({"detail": "Authentication required."}, 401)
        if mode == "password" and request.method not in SAFE and not csrf_valid(request):
            audit(request, "csrf_denied", 403)
            return public_response(
                {"detail": "Request verification failed. Reload and retry."}, 403
            )
        # Local-only development retains command-line access; exposed/authenticated instances
        # always enforce shared database-backed rate and concurrency budgets.
        if mode == "password":
            request.security_lease = acquire(request)
            if request.security_lease is None:
                audit(request, "request_limited", 429)
                response = public_response({"detail": "Too many requests. Try again shortly."}, 429)
                response["Retry-After"] = "60"
                return response
        match = re.match(r"^/api/(?:analyses|requests|questions)/([0-9a-fA-F-]{36})(?:/|$)", request.path)
        if match:
            from .models import Request

            try:
                identifier = uuid.UUID(match[1])
            except ValueError:
                return public_response({"detail": "Not found"}, 404)
            state = Request.all_objects.filter(pk=identifier).values_list("discussion_state", flat=True).first()
            if state and state.get("private") and state.get("owner") != request.discussion_actor:
                return public_response({"detail": "Not found"}, 404)
        return None

    def process_exception(self, request, exception):
        if request.path.startswith("/api/"):
            if getattr(request, "access_mode", None) == "password":
                audit(request, "request_error", 500)
            return public_response({"detail": "The request could not be completed."}, 500)
        return None

    def process_response(self, request, response):
        if getattr(request, "new_discussion_cookie", None) and (request.path == "/api/access/session" or request.method not in SAFE):
            from .discussion_access import AGE, COOKIE

            response.set_cookie(COOKIE, request.new_discussion_cookie, max_age=AGE,
                                httponly=True, secure=request.is_secure(), samesite="Lax")
        if request.path.startswith("/api/"):
            release(getattr(request, "security_lease", None))
            if (
                request.method not in SAFE
                and getattr(request, "access_mode", None) == "password"
                and request.path not in ACCESS_PATHS
            ):
                audit(request, "write", response.status_code)
            response["Cache-Control"] = "no-store, private"
            response["X-Content-Type-Options"] = "nosniff"
            response["Referrer-Policy"] = "same-origin"
            if request.is_secure() and settings.CSRF_COOKIE_NAME in response.cookies:
                response.cookies[settings.CSRF_COOKIE_NAME]["secure"] = True
        return response
