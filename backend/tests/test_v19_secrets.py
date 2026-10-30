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


@pytest.mark.parametrize("secret,text", [
    ("ee", "Keep weekly quota observations."),
    ("test", "Test connection and retry the latest analysis."),
    ("admin", "Open the administration panel."),
])
def test_short_credentials_do_not_replace_word_fragments(secret, text):
    from core.sensitive_data import contains_credentials

    assert redact(text, [secret]) == text
    assert not contains_credentials(text, [secret])


@pytest.mark.parametrize("secret", ["ee", "test", "admin", "fixture-long-private-token"])
def test_actual_short_and_long_credentials_and_encodings_remain_hidden(secret):
    from core.sensitive_data import contains_credentials

    for value in (secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode()):
        assert redact({"nested": [value, f"password={value};"]}, [secret]) == {
            "nested": ["[REDACTED]", "password=[REDACTED];"]
        }
        assert contains_credentials(f"password={value};", [secret])
    assert "reader" not in redact(f"postgresql://reader:{secret}@host/db", [secret])
    assert redact("prefix" + secret + "suffix", [secret]) == (
        "prefix" + secret + "suffix" if len(secret) < 8 else "prefix[REDACTED]suffix"
    )


def test_redaction_markers_are_stable_across_nested_and_repeated_redaction():
    values = {"body": ["[REDACTED]", "RE", "fixture-long-private-token"]}
    expected = {"body": ["[REDACTED]", "[REDACTED]", "[REDACTED]"]}
    assert redact(values, ["fixture-long-private-token", "RE"]) == expected
    assert redact(expected, ["RE"]) == expected
    assert redact("pass-long-private", ["pass", "pass-long-private"]) == "[REDACTED]"


def test_short_secret_does_not_corrupt_request_metadata_or_stored_text(client, environment):
    GitConnection.objects.create(name="Source", provider="gitlab", base_url="https://git.invalid", secret=encrypt("ee"))
    request = Request.objects.create(environment=environment, need="Keep weekly observations.")
    response = client.get(f"/api/requests/{request.pk}")
    assert response.status_code == 200
    assert response.json()["need"] == "Keep weekly observations."
    request.refresh_from_db()
    assert request.need == "Keep weekly observations."


def test_instruction_validation_ignores_word_fragments_but_rejects_real_credentials():
    from unittest.mock import patch

    from ninja.errors import HttpError

    from core.environment_context import reject_credentials

    with patch("core.sensitive_data.configured_secrets", return_value=["ee"]):
        reject_credentials("Keep weekly observations.")
        with pytest.raises(HttpError, match="credentials"):
            reject_credentials("password=ee")


def test_instruction_word_fragments_do_not_block_settings_or_execution(client, monkeypatch):
    from core.models import InstanceSettings
    from core.orchestration_settings import get_config

    stored = "Keep weekly observations."
    row, _ = InstanceSettings.objects.update_or_create(pk=1, defaults={"orchestration": {"global_instructions": stored}})
    monkeypatch.setattr("core.sensitive_data.configured_secrets", lambda: ["ee"])
    assert get_config("2.4")["global_instructions"] == stored
    response = client.get("/api/orchestration-settings")
    assert response.status_code == 200
    assert response.json()["global_instructions"] == stored
    assert not response.json().get("global_instructions_requires_review", False)
    row.refresh_from_db()
    assert row.orchestration["global_instructions"] == stored


def test_public_connector_username_is_not_confused_with_its_short_password(client, environment):
    connector = TicketConnector.objects.create(
        name="Local GLPI", platform="glpi", environment=environment,
        base_url="http://glpi.invalid/apirest.php", username="admin", secret=encrypt("admin"),
    )
    connector.environments.add(environment)
    response = client.get("/api/ticket-connectors")
    assert response.status_code == 200
    row = next(item for item in response.json() if item["id"] == connector.pk)
    assert row["username"] == "admin"
    assert "secret" not in row
    assert redact({"username": "admin", "body": "password=admin"}, ["admin"], public_identifiers=("username",)) == {
        "username": "admin", "body": "password=[REDACTED]"
    }
    assert redact({"username": "fixture-long-private-token"}, ["fixture-long-private-token"], public_identifiers=("username",)) == {"username": "[REDACTED]"}


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
