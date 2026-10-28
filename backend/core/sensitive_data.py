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


def credential_pattern(secrets):
    """Match short credentials as whole tokens, never as fragments of ordinary words."""
    patterns = set()
    for secret in filter(None, secrets):
        for encoded in {secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode()}:
            literal = re.escape(encoded)
            pattern = r"(?<!\w)" + literal + r"(?!\w)" if len(secret) < 8 else literal
            patterns.add((len(encoded), len(secret) >= 8, pattern))
    # A single substitution also prevents one secret from damaging an existing marker.
    return re.compile(r"\[REDACTED\]" + ("|" + "|".join(item[2] for item in sorted(patterns, reverse=True)) if patterns else ""))


def contains_credentials(text, secrets):
    return any(match.group() != "[REDACTED]" for match in credential_pattern(secrets).finditer(text))


def redact(value, secrets, *, public_identifiers=()):
    """Redact credentials recursively while preserving unrelated labels and identifiers."""
    pattern = credential_pattern(secrets)
    identifier_pattern = credential_pattern([secret for secret in secrets if len(secret) >= 8])

    def visit(item, public_identifier=False):
        if isinstance(item, str):
            item = (identifier_pattern if public_identifier else pattern).sub("[REDACTED]", item)
            item = re.sub(r"(?i)(https?://|postgres(?:ql)?://)([^/\s:@]+):([^/@\s]+)@", r"\1[REDACTED]@", item)
            item = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,})", "[REDACTED]", item)
            return re.sub(r"\bAIza[0-9A-Za-z_-]{35}\b", "[REDACTED]", item)
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, dict):
            return {key: visit(child, key in public_identifiers and isinstance(child, str)) for key, child in item.items()}
        return item

    return visit(value)


def git_credentials():
    """Repository read credentials cannot authorize issue publication."""
    values = set()
    for model in (GitConnection, GitHubConnection):
        for value in model.objects.values_list("secret", flat=True):
            if value:
                values.add(decrypt(value))
    return values
