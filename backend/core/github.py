import re

import httpx

from .models import GitHubConnection
from .secrets import decrypt


def validate_repository(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("Expected repository: organization/name")
    if any(part in {".", ".."} for part in value.split("/")):
        raise ValueError("Invalid repository")
    return value


def token():
    connection = GitHubConnection.objects.filter(pk=1).first()
    if not connection or not connection.secret:
        raise ValueError("Configure the GitHub connection")
    return decrypt(connection.secret)


def get(path, params=None):
    with httpx.Client(timeout=20) as client:
        response = client.get(
            "https://api.github.com" + path,
            params=params,
            headers={"Authorization": "Bearer " + token(), "Accept": "application/vnd.github+json"},
        )
    if response.status_code != 200:
        raise ValueError(f"GitHub unavailable (HTTP {response.status_code})")
    return response.json()


def paginated(path, page=1):
    return get(path, {"per_page": 100, "page": page})
