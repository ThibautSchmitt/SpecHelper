"""Global procedure authoring and shared, metadata-only quota refresh."""

import copy
from datetime import timedelta

import pytest
from django.utils import timezone

from core.global_skills import catalog
from core.library import DefinitionIn, check_definition, save_definition
from core.models import AIConnection, AIIdentity, LibraryRevision


@pytest.mark.django_db
def test_new_skill_needs_no_provider_or_capability_selection():
    value = {
        "slug": "sql-exceptions",
        "name": "SQL exceptions",
        "objective": "Count rare states.",
        "instructions": "Inspect PostgreSQL populations with bounded read-only queries.",
    }
    checked = check_definition("skill", value)
    assert checked["valid"]
    assert checked["definition"]["compatibility"] == []
    assert checked["definition"]["required_capabilities"] == ["read_database"]
    saved = save_definition("skill", DefinitionIn(**value))
    for provider in ("codex", "claude"):
        connection = AIConnection.objects.create(agent=provider)
        without_db = next(
            item for item in catalog(connection)["registry"] if item["slug"] == saved["slug"]
        )
        assert without_db["provider_compatible"] and not without_db["applicable"]
        assert without_db["missing_capabilities"] == ["read_database"]
        assert saved["slug"] in {item["slug"] for item in catalog(connection, True)["definitions"]}


@pytest.mark.django_db
def test_current_global_compatibility_preserves_legacy_revision():
    from core.models import SkillDefinition

    item = SkillDefinition.objects.create(
        slug="legacy-readable",
        name="Legacy review",
        objective="Review boundaries.",
        instructions="Inspect project sources.",
        compatibility=["codex"],
    )
    original = copy.deepcopy(item.compatibility)
    connection = AIConnection.objects.create(agent="claude")
    loaded = next(
        value for value in catalog(connection)["definitions"] if value["slug"] == item.slug
    )
    assert loaded["compatibility"] == []
    assert (
        LibraryRevision.objects.get(kind="skill", slug=item.slug, version=1).definition[
            "compatibility"
        ]
        == original
    )
    item.refresh_from_db()
    assert item.compatibility == original


@pytest.mark.django_db
def test_web_metadata_does_not_grant_an_unavailable_tool():
    value = save_definition(
        "skill",
        DefinitionIn(
            slug="official-review",
            name="Official review",
            objective="Check official documentation.",
            instructions="Read official sources and record applicability.",
        ),
    )
    assert value["required_capabilities"] == ["read_web"]
    connection = AIConnection.objects.create(agent="codex")
    metadata = next(
        item for item in catalog(connection)["registry"] if item["slug"] == value["slug"]
    )
    assert not metadata["applicable"] and metadata["missing_capabilities"] == ["read_web"]
    available = catalog(connection, available_capabilities={"read_web", "structured_output"})
    assert value["slug"] in {item["slug"] for item in available["definitions"]}


@pytest.mark.django_db
def test_quota_refresh_is_cached_across_connections_without_an_inference(client, monkeypatch):
    identity = AIIdentity.objects.create(
        agent="codex", status="CONNECTED", availability="AVAILABLE"
    )
    first = AIConnection.objects.create(agent="codex", identity=identity)
    second = AIConnection.objects.create(agent="codex", identity=identity)
    calls = []

    def metadata(path, **kwargs):
        calls.append(path)
        assert path.startswith("/health?") and "quota=true" in path
        return {
            "status": "CONNECTED",
            "quota_status": {"state": "available", "reason": ""},
            "quota_windows": {
                "session": {"used_percent": 55, "observed_at": timezone.now().isoformat()}
            },
        }

    monkeypatch.setattr("core.ai_api.runtime_call", metadata)
    assert (
        client.post(f"/api/ai-connections/{first.pk}/quota/refresh").json()["quota_refresh_state"]
        == "refreshed"
    )
    response = client.post(f"/api/ai-connections/{second.pk}/quota/refresh")
    assert response.status_code == 200 and response.json()["quota_refresh_state"] == "cached"
    assert len(calls) == 1
    assert response.json()["quota_windows"]["session"]["used_percent"] == 55


@pytest.mark.django_db
def test_failed_refresh_keeps_observed_quota_and_throttles_retry(client, monkeypatch):
    observed = (timezone.now() - timedelta(minutes=10)).isoformat()
    identity = AIIdentity.objects.create(
        agent="codex",
        status="CONNECTED",
        availability="QUOTA_EXHAUSTED",
        quota_windows={"session": {"used_percent": 100, "observed_at": observed}},
    )
    connection = AIConnection.objects.create(agent="codex", identity=identity)
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(True)
        raise ValueError("private provider error")

    monkeypatch.setattr("core.ai_api.runtime_call", unavailable)
    response = client.post(f"/api/ai-connections/{connection.pk}/quota/refresh")
    assert response.status_code == 200
    assert response.json()["quota_refresh_state"] == "error"
    assert response.json()["quota_status"]["reason"] == "refresh_failed"
    assert response.json()["quota_windows"]["session"]["observed_at"] == observed
    assert "private provider" not in response.content.decode()
    assert (
        client.post(f"/api/ai-connections/{connection.pk}/quota/refresh").json()[
            "quota_refresh_state"
        ]
        == "cached"
    )
    assert calls == [True]


@pytest.mark.django_db
def test_busy_quota_refresh_never_calls_provider(client, monkeypatch):
    identity = AIIdentity.objects.create(agent="codex", status="CONNECTED", availability="BUSY")
    connection = AIConnection.objects.create(agent="codex", identity=identity)
    monkeypatch.setattr(
        "core.ai_api.runtime_call",
        lambda *args, **kwargs: pytest.fail("Busy identity must not be probed"),
    )
    assert (
        client.post(f"/api/ai-connections/{connection.pk}/quota/refresh").json()[
            "quota_refresh_state"
        ]
        == "busy"
    )


@pytest.mark.django_db(transaction=True)
def test_another_browser_refresh_returns_without_waiting_for_identity_lock(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, transaction
    from django.db import connection as database

    if database.vendor != "postgresql":
        pytest.skip("Shared quota row locking requires PostgreSQL")
    identity = AIIdentity.objects.create(
        agent="codex", status="CONNECTED", availability="AVAILABLE"
    )
    configured = AIConnection.objects.create(agent="codex", identity=identity)
    acquired, release = Event(), Event()

    def hold_refresh():
        close_old_connections()
        try:
            with transaction.atomic():
                AIIdentity.objects.select_for_update().get(pk=identity.pk)
                acquired.set()
                assert release.wait(10)
        finally:
            close_old_connections()

    monkeypatch.setattr(
        "core.ai_api.runtime_call",
        lambda *args, **kwargs: pytest.fail("A concurrent refresh owns this quota identity"),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(hold_refresh)
        assert acquired.wait(5)
        try:
            result = client.post(f"/api/ai-connections/{configured.pk}/quota/refresh")
            assert result.status_code == 200 and result.json()["quota_refresh_state"] == "pending"
        finally:
            release.set()
        future.result(timeout=5)
