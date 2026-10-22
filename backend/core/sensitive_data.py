"""Keep configured technical credentials outside AI prompts and public conclusions."""

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
    return sorted(filter(None, values), key=len, reverse=True)


def redact(value, secrets):
    """Redact exact configured credentials recursively, without logging their values."""
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    return value
