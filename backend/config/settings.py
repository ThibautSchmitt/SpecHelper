import os
from pathlib import Path

from core.control import control_token, private_value

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SPECHELPER_DATA_DIR", str(BASE_DIR.parent / ".local")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or private_value(
    DATA_DIR / "django.key", create=True
)
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,backend,testserver").split(",")
INSTALLED_APPS = ["django.contrib.contenttypes", "core"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.boundary_response.BoundaryResponseMiddleware",
    "core.middleware.SameOriginMiddleware",
    "core.middleware.SecureCsrfMiddleware",
    "core.middleware.AccessMiddleware",
]
ROOT_URLCONF = "config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "app.sqlite3"}}
if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "NAME": os.environ.get("POSTGRES_DB", "spechelper"),
            "USER": os.environ.get("POSTGRES_USER", "spechelper"),
            "PASSWORD": os.environ["POSTGRES_PASSWORD"],
            "CONN_MAX_AGE": 60,
        }
    }
MEDIA_ROOT = DATA_DIR / "requests"
DATA_UPLOAD_MAX_MEMORY_SIZE = 26 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
RUNTIME_URL = os.environ.get("RUNTIME_URL", "http://agent-runtime:8090")
CLI_MAINTENANCE_URL = os.environ.get("CLI_MAINTENANCE_URL", "")
CLI_MAINTENANCE_TOKEN_FILE = os.environ.get("CLI_MAINTENANCE_TOKEN_FILE", "/cli-control/token")
ANALYSIS_POLICY_FILE = os.environ.get("SPECHELPER_ANALYSIS_POLICY_FILE", "")
RUNTIME_TOKEN = control_token(create=True, default_path=str(DATA_DIR / "control.token"))
TRUSTED_ORIGINS = os.environ.get(
    "TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"content_free_web": {"()": "core.security_logging.ContentFreeWebLogFilter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "filters": ["content_free_web"]}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Remote deployments use shared application access; localhost-only mode has no user tenancy.
ACCESS_PASSWORD_HASH = os.environ.get("SPECHELPER_ACCESS_PASSWORD_HASH", "")
ACCESS_PASSWORD_FILE = os.environ.get("SPECHELPER_ACCESS_PASSWORD_FILE", "")
ACCESS_LOCAL_ONLY = os.environ.get("SPECHELPER_LOCAL_ONLY", "1") == "1"
ACCESS_BIND_ADDRESS = os.environ.get("BIND_ADDRESS", "127.0.0.1")
ACCESS_REQUIRE_HTTPS = os.environ.get("SPECHELPER_REQUIRE_HTTPS", "0") == "1"
ACCESS_COOKIE_NAME = "spechelper_session"
ACCESS_SESSION_SECONDS = max(
    300, min(86400, int(os.environ.get("SPECHELPER_SESSION_SECONDS", "28800")))
)
ACCESS_LOGIN_RATE = max(1, min(30, int(os.environ.get("SPECHELPER_LOGIN_RATE", "5"))))
ACCESS_READ_RATE = max(30, min(10000, int(os.environ.get("SPECHELPER_READ_RATE", "600"))))
ACCESS_WRITE_RATE = max(10, min(1000, int(os.environ.get("SPECHELPER_WRITE_RATE", "120"))))
ACCESS_CONCURRENCY = max(1, min(64, int(os.environ.get("SPECHELPER_CONCURRENCY", "16"))))
# Background AI invocations share quotas, but keep independent conversation sessions.
AI_ACCOUNT_CONCURRENCY = max(1, min(32, int(os.environ.get("SPECHELPER_AI_ACCOUNT_CONCURRENCY", "4"))))
AI_CONCURRENCY = max(1, min(64, int(os.environ.get("SPECHELPER_AI_CONCURRENCY", "8"))))
ACCESS_LEASE_SECONDS = 90
ACCESS_MAX_REQUEST_BYTES = 26 * 1024 * 1024
SECURITY_AUDIT_RETENTION_DAYS = max(
    1, min(365, int(os.environ.get("SPECHELPER_AUDIT_RETENTION_DAYS", "30")))
)
CSRF_COOKIE_NAME = "spechelper_csrf"
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = ACCESS_REQUIRE_HTTPS
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = TRUSTED_ORIGINS
# Forwarded TLS is trusted only when the deployment explicitly enables its trusted proxy.
if os.environ.get("SPECHELPER_TRUST_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
