import json
from unittest.mock import patch

import httpx
import pytest

from core.models import Environment, GitHubConnection, Job
from core.secrets import decrypt

pytestmark = pytest.mark.django_db


def test_github_connect_discover_paginate_and_keep_token_private(client, storage):
    visited = []

    def transport(request):
        assert request.headers["Authorization"] == "Bearer fixture-github-token"
        assert request.url.host == "api.github.com"
        visited.append(str(request.url))
        data = {
            "/user": {"login": "fixture-company"},
            "/user/orgs": [{"login": "company"}],
            "/user/repos": [
                {"full_name": "company/backend", "private": True, "default_branch": "main"}
            ],
            "/repos/company/backend/branches": [{"name": "develop"}],
        }
        return httpx.Response(200, json=data[request.url.path])

    original = httpx.Client
    with patch(
        "core.github.httpx.Client",
        side_effect=lambda **kwargs: original(transport=httpx.MockTransport(transport), **kwargs),
    ):
        response = client.put(
            "/api/connections/github",
            data=json.dumps({"token": "fixture-github-token"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["account"] == "fixture-company"
        assert client.get("/api/github/organizations").json() == [{"login": "company"}]
        assert (
            client.get("/api/github/repositories?page=2").json()[0]["full_name"]
            == "company/backend"
        )
        assert client.get("/api/github/branches?repository=company/backend").json() == [
            {"name": "develop"}
        ]
    connection = GitHubConnection.objects.get()
    assert connection.secret != "fixture-github-token"
    assert decrypt(connection.secret) == "fixture-github-token"
    assert "fixture-github-token" not in client.get("/api/connections").content.decode()
    assert any("page=2" in url for url in visited)
    assert client.get("/api/github/branches?repository=../../etc/passwd").status_code == 422


def test_create_environment_without_database_queues_sync_and_rejects_duplicates(client):
    payload = {
        "name": "Validation",
        "repositories": [{"repository": "Company/Backend", "branch": "develop"}],
        "database_id": None,
    }
    result = client.post(
        "/api/environments", data=json.dumps(payload), content_type="application/json"
    )
    assert result.status_code == 201
    assert result.json()["database_id"] is None
    assert Environment.objects.get().repositories.get().repository == "company/backend"
    assert Job.objects.get().kind == "sync"
    assert (
        client.post(
            "/api/environments", data=json.dumps(payload), content_type="application/json"
        ).status_code
        == 409
    )
    payload["name"] = "Duplicate repo"
    payload["repositories"].append({"repository": "company/backend", "branch": "main"})
    assert (
        client.post(
            "/api/environments", data=json.dumps(payload), content_type="application/json"
        ).status_code
        == 422
    )
