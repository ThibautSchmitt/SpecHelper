"""Credential separation, redaction and private key handling at observable boundaries."""

import base64
import json
from urllib.parse import quote

import pytest
from ninja.testing import TestClient

from core.models import GitConnection, Request, TicketConnector
from core.secrets import cipher, decrypt, encrypt
from core.sensitive_data import redact
from core.ticket_api import router
from core.ticket_providers import GitHubProvider, TicketProviderError

pytestmark = pytest.mark.django_db


def test_exact_encoded_and_url_credentials_are_redacted():
    secret = "fixture-private+token/with-symbols"
    for value in (secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode()):
        assert redact({"text": value}, [secret]) == {"text": "[REDACTED]"}
    assert "password" not in redact("postgresql://reader:password@host/db", [])


def test_known_secret_cannot_escape_in_stored_request_api_or_export(client, environment, storage):
    token = "fixture-business-api-private-token"
    GitConnection.objects.create(name="Sources", provider="github", base_url="https://github.com", secret=encrypt(token))
    request = Request.objects.create(environment=environment, need="A pasted credential " + token)
    response = client.get(f"/api/requests/{request.pk}")
    assert response.status_code == 200
    assert token not in response.content.decode()
    assert "[REDACTED]" in response.content.decode()
    request.refresh_from_db()
    assert token in request.need  # The boundary does not mutate historical records.


def test_publication_never_reuses_git_source_token(environment, storage):
    source = "fixture-source-only-credential"
    GitConnection.objects.create(name="Source", provider="github", base_url="https://github.com", secret=encrypt(source))
    payload = {"environment_id": environment.pk, "name": "Issues", "platform": "github", "base_url": "https://api.github.com", "secret": source}
    client = TestClient(router)
    response = client.post("/ticket-connectors", json=payload)
    assert response.status_code == 422
    assert source not in json.dumps(response.json())
    assert TicketConnector.objects.count() == 0
    response = client.post("/ticket-connectors", json={**payload, "secret": "fixture-dedicated-issue-token"})
    assert response.status_code == 200
    connector = TicketConnector.objects.get(pk=response.json()["id"])
    assert decrypt(connector.secret) == "fixture-dedicated-issue-token"
    # Credentials rotated to match a source are also refused at actual adapter execution.
    connector.secret = encrypt(source)
    with pytest.raises(TicketProviderError, match="distinct"):
        GitHubProvider(connector)


def test_encryption_key_is_private_regular_and_separate_from_database(settings, tmp_path, monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    key = tmp_path / "keys" / "encryption.key"
    monkeypatch.setenv("ENCRYPTION_KEY_FILE", str(key))
    ciphertext = encrypt("fixture-private-value")
    assert decrypt(ciphertext) == "fixture-private-value"
    assert key.stat().st_mode & 0o077 == 0
    assert str(key) != str(settings.DATABASES["default"]["NAME"])
    key.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        cipher()
    key.unlink()
    target = tmp_path / "other"
    target.write_text("not-a-key")
    key.symlink_to(target)
    with pytest.raises(OSError):
        cipher()
    assert target.read_text() == "not-a-key"
