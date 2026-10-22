from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from core.management.commands.connect_github import Command
from core.models import ConnectionAttempt, GitConnection, GitHubConnection
from core.secrets import decrypt, encrypt

pytestmark = pytest.mark.django_db(transaction=True)


class CompletedLogin:
    def __init__(self, provider, complete, update):
        self.complete = complete

    def start(self):
        self.complete(None, {})

    def public(self):
        return {"status": "CONNECTED"}


@pytest.mark.parametrize("cancel_during_verification", [False, True])
def test_browser_authorization_never_retargets_another_source_or_publication_credentials(
    cancel_during_verification,
):
    source = GitConnection.objects.create(
        name="Second account", provider="github", base_url="https://github.com"
    )
    other = GitConnection.objects.create(
        name="First account",
        provider="github",
        base_url="https://github.com",
        secret=encrypt("fixture-first-source"),
    )
    legacy, _ = GitHubConnection.objects.update_or_create(
        pk=1, defaults={"secret": encrypt("fixture-publication-only")}
    )
    attempt = ConnectionAttempt.objects.create(
        provider="github",
        git_connection=source,
        status="AWAITING_USER",
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    response = Mock(status_code=200)
    response.json.return_value = {"login": "fixture-second-account"}

    def verify(*args, **kwargs):
        if cancel_during_verification:
            ConnectionAttempt.objects.filter(pk=attempt.pk).update(
                status="CANCELLED", git_connection=None
            )
        return response

    with (
        patch("core.management.commands.connect_github.TerminalLogin", CompletedLogin),
        patch("core.management.commands.connect_github.close_old_connections"),
        patch(
            "core.management.commands.connect_github.subprocess.check_output",
            return_value="fixture-second-source",
        ),
        patch("core.management.commands.connect_github.httpx.Client") as client,
    ):
        client.return_value.__enter__.return_value.get.side_effect = verify
        if cancel_during_verification:
            with pytest.raises(ValueError, match="cancelled"):
                Command().handle(str(attempt.pk))
        else:
            Command().handle(str(attempt.pk))
    source.refresh_from_db()
    other.refresh_from_db()
    legacy.refresh_from_db()
    assert decrypt(other.secret) == "fixture-first-source"
    assert decrypt(legacy.secret) == "fixture-publication-only"
    assert (
        (source.secret == "")
        if cancel_during_verification
        else (decrypt(source.secret) == "fixture-second-source")
    )


def test_all_ai_configurations_can_be_removed_without_breaking_connection_overview(client):
    from core.models import AIConnection
    from core.providers import ensure_connections

    ensure_connections()
    AIConnection.objects.all().delete()
    response = client.get("/api/connections")
    assert response.status_code == 200
    assert response.json()["ais"] == []
    assert response.json()["ai"]["status"] == "DISCONNECTED"
    assert client.post("/api/connections/ai/test").status_code == 404
