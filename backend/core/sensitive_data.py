"""Keep configured technical credentials outside AI prompts and public conclusions."""

import base64
import os
import re
from urllib.parse import quote

from .models import DatabaseConnection, GitConnection, GitHubConnection, TicketConnector
from .secrets import decrypt


def configured_secrets():
    values = set()
    for model, fields in (
        (GitHubConnection, ("secret",)),
        (GitConnection, ("secret",)),
        (DatabaseConnection, ("secret",)),
        (TicketConnector, ("secret", "app_token")),
    ):
        for row in model.objects.values_list(*fields):
            for encrypted in row:
                if encrypted:
                    values.add(decrypt(encrypted))
    for key in ("ENCRYPTION_KEY", "DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "RUNTIME_TOKEN"):
        if os.environ.get(key):
            values.add(os.environ[key])
    return sorted(filter(None, values), key=len, reverse=True)


def redact(value, secrets):
    """Redact exact configured credentials recursively, without logging their values."""
    if isinstance(value, str):
        for secret in secrets:
            for encoded in {secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode()}:
                value = value.replace(encoded, "[REDACTED]")
        value = re.sub(r"(?i)(https?://|postgres(?:ql)?://)([^/\s:@]+):([^/@\s]+)@", r"\1[REDACTED]@", value)
        value = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,})", "[REDACTED]", value)
        value = re.sub(r"\bAIza[0-9A-Za-z_-]{35}\b", "[REDACTED]", value)
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    return value


def git_credentials():
    """Repository read credentials cannot authorize issue publication."""
    values = set()
    for model in (GitConnection, GitHubConnection):
        for value in model.objects.values_list("secret", flat=True):
            if value:
                values.add(decrypt(value))
    return values
