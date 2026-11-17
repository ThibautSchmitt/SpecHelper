"""Favorite metadata is scoped to source connections, never an authorization grant."""
import json
from unittest.mock import Mock

import pytest

from core.git_sources import SourceError
from core.models import GitConnection, GitRepository
from core.secrets import encrypt

pytestmark = pytest.mark.django_db


@pytest.fixture
def favorite_source(monkeypatch):
    connection = GitConnection.objects.create(name="Source", provider="gitlab", base_url="https://git.example.test", secret=encrypt("fixture-secret"))
    source = GitRepository.objects.create(connection=connection, provider="gitlab", instance=connection.base_url,
        remote_id="17", path="team/project", name="project", clone_url=connection.base_url + "/team/project.git")
    provider = Mock()
    provider.project.return_value = source
    factory = Mock(return_value=provider)
    monkeypatch.setattr("core.git_source_api.Provider", factory)
    return source, provider, factory


def put(client, source, reference="", favorite=True):
    return client.put(f"/api/git-connections/{source.connection_id}/favorites", data=json.dumps({
        "remote_id": source.remote_id, "reference": reference, "favorite": favorite,
    }), content_type="application/json")


def test_favorites_persist_deduplicate_and_distinguish_branch_from_tag(client, favorite_source):
    source, provider, _ = favorite_source
    assert client.get("/api/git-favorites").json() == []
    assert put(client, source).json()["favorite"] is True
    for ref in ["release/v1", "tag:release/v1", "release/v1"]:
        assert put(client, source, ref).status_code == 200
    source.refresh_from_db()
    assert source.favorite_refs == ["release/v1", "tag:release/v1"]
    assert provider.branch.call_args.args == (source, "release/v1")
    saved = client.get("/api/git-favorites").json()
    assert saved[0]["git_connection_id"] == source.connection_id
    assert saved[0]["favorite_refs"] == source.favorite_refs
    assert "secret" not in saved[0] and "clone_url" not in saved[0]
    assert put(client, source, "release/v1", False).json()["favorite_refs"] == ["tag:release/v1"]
    assert put(client, source, "", False).json()["favorite"] is False
    assert len(client.get("/api/git-favorites").json()) == 1  # Tag remains reachable.
    assert put(client, source, "tag:release/v1", False).status_code == 200
    assert client.get("/api/git-favorites").json() == []


def test_removing_an_unavailable_favorite_does_not_contact_the_provider(client, favorite_source):
    source, provider, factory = favorite_source
    source.favorite = True
    source.favorite_refs = ["gone"]
    source.save()
    source.connection.enabled = False
    source.connection.save()
    assert put(client, source, "gone", False).status_code == 200
    assert put(client, source, "", False).status_code == 200
    factory.assert_not_called()
    provider.project.assert_not_called()


def test_favorites_do_not_leak_between_connections_or_survive_unverified_additions(client, favorite_source):
    source, provider, _ = favorite_source
    source.favorite = True
    source.save()
    other = GitConnection.objects.create(name="Other", provider="gitlab", base_url="https://other.example.test")
    sibling = GitRepository.objects.create(connection=other, provider="gitlab", instance=other.base_url,
        remote_id="17", path="team/project", name="project", clone_url=other.base_url + "/team/project.git")
    assert put(client, sibling, "", False).status_code == 200
    source.refresh_from_db()
    assert source.favorite is True
    provider.branch.side_effect = SourceError("The selected Git branch is unavailable.")
    assert put(client, source, "missing").status_code == 422
    source.refresh_from_db()
    assert source.favorite_refs == []
    assert [row["git_connection_id"] for row in client.get("/api/git-favorites").json()] == [source.connection_id]


def test_refreshing_discovery_preserves_favorites_and_limits_versions(client, favorite_source):
    from core.git_sources import Provider

    source, _, _ = favorite_source
    source.favorite = True
    source.favorite_refs = [f"release/{number}" for number in range(100)]
    source.save()
    actual = Provider(source.connection)
    actual._record({"id": 17, "path_with_namespace": "team/project", "name": "Renamed", "http_url_to_repo": source.clone_url})
    source.refresh_from_db()
    assert source.name == "Renamed" and source.favorite and len(source.favorite_refs) == 100
    assert put(client, source, "overflow").status_code == 422
    assert put(client, source, "release/0").status_code == 200
