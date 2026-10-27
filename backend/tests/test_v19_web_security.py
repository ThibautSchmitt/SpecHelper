"""Shared access, CSRF, identifier privacy and bounded content-free audit checks."""

import json
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client, RequestFactory
from django.utils import timezone

from core.models import Environment, Request
from core.security_models import AccessSession, SecurityBucket, SecurityEvent
from core.web_security import acquire, release

pytestmark = pytest.mark.django_db


@pytest.fixture
def protected(settings):
    settings.ACCESS_PASSWORD_HASH = make_password("synthetic-shared-team-password")
    settings.ACCESS_PASSWORD_FILE = ""
    settings.ACCESS_REQUIRE_HTTPS = False
    settings.ACCESS_BIND_ADDRESS = "0.0.0.0"
    settings.ALLOWED_HOSTS = ["testserver", "team.example", "backend", "localhost"]
    settings.TRUSTED_ORIGINS = ["http://testserver", "https://team.example"]
    settings.CSRF_TRUSTED_ORIGINS = settings.TRUSTED_ORIGINS
    return Client(enforce_csrf_checks=True)


def login(client, secure=False, password="synthetic-shared-team-password"):
    session = client.get("/api/access/session", secure=secure)
    token = session.json()["csrf_token"]
    response = client.post(
        "/api/access/login",
        data=json.dumps({"password": password}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
        secure=secure,
        **({"HTTP_ORIGIN": "https://testserver"} if secure else {}),
    )
    return response


def test_all_business_and_admin_ids_require_authentication(protected):
    environment = Environment.objects.create(name="Private team")
    request = Request.objects.create(environment=environment, need="Private request")
    paths = [
        "/api/settings",
        "/api/requests",
        "/api/analyses",
        "/api/analyses/overview",
        f"/api/analyses/{request.pk}",
        "/api/analyses/11111111-1111-4111-8111-111111111111",
        f"/api/requests/{request.pk}",
        "/api/requests/11111111-1111-4111-8111-111111111111",
        f"/api/requests/{request.pk}/attachments/1",
        f"/api/requests/{request.pk}/versions/1/artifacts/goal.md",
        "/api/connections",
        "/api/docs",
        "/api/openapi.json",
    ]
    for path in paths:
        response = protected.get(path)
        assert response.status_code == 401, (path, response.content)
        assert response.json() == {"detail": "Authentication required."}
        assert b"Private" not in response.content
    assert protected.get("/api/health").json() == {"status": "ok"}


def test_login_rotates_session_and_csrf_and_logout_revokes(protected):
    bootstrap = protected.get("/api/access/session").json()
    assert not bootstrap["authenticated"]
    assert (
        protected.post(
            "/api/access/login",
            data=json.dumps({"password": "synthetic-shared-team-password"}),
            content_type="application/json",
        ).status_code
        == 403
    )
    response = login(protected)
    assert response.status_code == 200, response.content
    first_cookie = protected.cookies["spechelper_session"].value
    assert response.cookies["spechelper_session"]["httponly"]
    assert response.cookies["spechelper_session"]["samesite"] == "Strict"
    assert response.json()["csrf_token"] != bootstrap["csrf_token"]
    assert AccessSession.objects.count() == 1
    assert protected.get("/api/settings").status_code == 200
    assert (
        protected.put("/api/settings", data="{}", content_type="application/json").status_code
        == 403
    )
    second = login(protected)
    assert second.status_code == 200
    assert protected.cookies["spechelper_session"].value != first_cookie
    assert AccessSession.objects.count() == 1
    old = Client()
    old.cookies["spechelper_session"] = first_cookie
    assert old.get("/api/settings").status_code == 401
    token = second.json()["csrf_token"]
    assert protected.post("/api/access/logout", HTTP_X_CSRFTOKEN=token).status_code == 200
    assert AccessSession.objects.count() == 0
    assert protected.get("/api/settings").status_code == 401


def test_https_cookie_secure_and_expiration_and_credential_rotation(protected, settings):
    settings.ACCESS_REQUIRE_HTTPS = True
    assert protected.get("/api/settings").status_code == 403
    response = login(protected, secure=True)
    assert response.status_code == 200, response.content
    assert response.cookies["spechelper_session"]["secure"]
    assert response.cookies["spechelper_csrf"]["secure"]
    assert protected.get("/api/settings", secure=True).status_code == 200
    AccessSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert protected.get("/api/settings", secure=True).status_code == 401
    assert login(protected, secure=True).status_code == 200
    settings.ACCESS_PASSWORD_HASH = make_password("rotated-synthetic-team-password")
    assert protected.get("/api/settings", secure=True).status_code == 401


def test_csrf_origin_host_and_shared_team_permissions(protected, settings):
    response = login(protected)
    token = response.json()["csrf_token"]
    payload = {
        "name": "Shared team",
        "primary_color": "#2563eb",
        "short_label": "",
        "language": "en",
        "allow_confrontation": False,
    }
    for headers in ({"HTTP_ORIGIN": "https://evil.example"}, {"HTTP_SEC_FETCH_SITE": "cross-site"}):
        assert (
            protected.put(
                "/api/settings",
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
                **headers,
            ).status_code
            == 403
        )
    assert protected.get("/api/settings", HTTP_HOST="evil.example").status_code == 400
    assert (
        protected.put(
            "/api/settings",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        ).status_code
        == 200
    )
    another = Client(enforce_csrf_checks=True)
    assert login(another).status_code == 200
    assert another.get("/api/settings").json()["name"] == "Shared team"
    assert protected.get("/api/settings")["Cache-Control"] == "no-store, private"


def test_exposed_instance_without_password_fails_closed(settings, client):
    settings.ACCESS_PASSWORD_HASH = ""
    settings.ACCESS_PASSWORD_FILE = ""
    settings.ACCESS_BIND_ADDRESS = "0.0.0.0"
    assert client.get("/api/settings").status_code == 503
    assert client.get("/api/access/session").json()["mode"] == "unconfigured"
    settings.ACCESS_BIND_ADDRESS = "127.0.0.1"
    settings.ALLOWED_HOSTS = ["testserver", "team.example"]
    assert client.get("/api/settings", HTTP_HOST="team.example").status_code == 503
    settings.TRUSTED_ORIGINS = ["http://testserver"]
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/settings", HTTP_X_FORWARDED_HOST="team.example").status_code == 503
    settings.TRUSTED_ORIGINS = ["https://team.example"]
    assert client.get("/api/settings").status_code == 503


def test_protected_password_file_permissions_and_revocation(settings, tmp_path, client):
    settings.ACCESS_PASSWORD_HASH = ""
    password_file = tmp_path / "access-password"
    password_file.write_text("synthetic-shared-team-password\n")
    password_file.chmod(0o600)
    settings.ACCESS_PASSWORD_FILE = str(password_file)
    assert login(client).status_code == 200
    password_file.chmod(0o644)
    assert client.get("/api/settings").status_code == 503
    password_file.chmod(0o600)
    password_file.unlink()
    assert client.get("/api/settings").status_code == 503


def test_login_rate_limit_and_audit_contains_no_payload_or_identifiers(protected, settings):
    settings.ACCESS_LOGIN_RATE = 2
    for _ in range(2):
        assert login(protected, password="sensitive-business-text-do-not-log").status_code == 401
    response = login(protected)
    assert response.status_code == 429
    assert response["Retry-After"] == "60"
    encoded = json.dumps(list(SecurityEvent.objects.values()), default=str)
    assert "sensitive-business-text-do-not-log" not in encoded
    assert "synthetic-shared-team-password" not in encoded
    assert "127.0.0.1" not in encoded
    assert set(SecurityEvent.objects.values_list("resource", flat=True)) == {"access"}


def test_request_rate_and_concurrency_limits_are_shared_database_state(protected, settings):
    assert login(protected).status_code == 200
    settings.ACCESS_READ_RATE = 2
    assert protected.get("/api/settings").status_code == 200
    assert protected.get("/api/settings").status_code == 200
    assert protected.get("/api/settings").status_code == 429
    SecurityBucket.objects.all().delete()
    settings.ACCESS_CONCURRENCY = 1
    request = RequestFactory().get("/api/settings")
    request.access_session = AccessSession.objects.first()
    first = acquire(request)
    assert first is not None
    assert acquire(request) is None
    release(first)
    assert acquire(request) is not None


def test_expired_leases_and_retention_cleanup_preserve_business_rows(protected, settings):
    environment = Environment.objects.create(name="Retained environment")
    item = Request.objects.create(environment=environment, need="Keep immutable business history")
    assert login(protected).status_code == 200
    SecurityEvent.objects.update(created_at=timezone.now() - timedelta(days=90))
    token = protected.get("/api/access/session").json()["csrf_token"]
    assert protected.post("/api/access/logout", HTTP_X_CSRFTOKEN=token).status_code == 200
    assert not SecurityEvent.objects.filter(
        created_at__lt=timezone.now() - timedelta(days=settings.SECURITY_AUDIT_RETENTION_DAYS)
    ).exists()
    assert Request.objects.get(pk=item.pk).need == "Keep immutable business history"


def test_large_request_fails_before_business_api_and_exception_details_are_generic(
    protected, settings
):
    assert login(protected).status_code == 200
    token = protected.get("/api/access/session").json()["csrf_token"]
    response = protected.post(
        "/api/settings",
        data="{}",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
        CONTENT_LENGTH=str(30 * 1024 * 1024),
    )
    assert response.status_code == 413


@pytest.mark.parametrize(
    "origin",
    ["http://testserver/path", "http://user@testserver", "https://testserver", "null", "http://["],
)
def test_local_origin_rejects_scheme_credentials_and_paths(settings, client, origin):
    settings.ACCESS_PASSWORD_HASH = ""
    settings.ACCESS_PASSWORD_FILE = ""
    settings.ACCESS_BIND_ADDRESS = "127.0.0.1"
    settings.TRUSTED_ORIGINS = ["http://testserver"]
    response = client.post(
        "/api/requests", data="{}", content_type="application/json", HTTP_ORIGIN=origin
    )
    assert response.status_code == 403


def test_web_logging_strips_injected_url_and_exception_text():
    import logging

    from core.security_logging import ContentFreeWebLogFilter

    record = logging.LogRecord(
        "django.request",
        logging.ERROR,
        __file__,
        1,
        "Failed /private?token=%s",
        ("synthetic-private-token",),
        (ValueError, ValueError("synthetic-private-error"), None),
    )
    assert ContentFreeWebLogFilter().filter(record)
    assert "synthetic" not in record.getMessage()
    assert record.exc_info is None


def test_invalid_password_hash_configuration_fails_closed(settings, client):
    settings.ACCESS_PASSWORD_HASH = "not-a-django-password-hash"
    settings.ACCESS_PASSWORD_FILE = ""
    assert client.get("/api/settings").status_code == 503
