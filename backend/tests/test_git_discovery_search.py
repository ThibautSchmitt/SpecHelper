"""Large remote collections must not be mistaken for an empty search result."""

from unittest.mock import patch

import httpx
import pytest

from core.git_sources import Provider
from core.models import GitConnection
from core.secrets import encrypt

pytestmark = pytest.mark.django_db


def github_project(identifier, path):
    return {"id": identifier, "full_name": path, "name": path.split("/")[-1],
            "clone_url": "https://github.com/" + path + ".git"}


def test_search_crosses_empty_remote_pages_without_skipping_the_continuation(client):
    connection = GitConnection.objects.create(
        provider="github", base_url="https://github.com", secret=encrypt("synthetic-read-token")
    )
    seen = []

    def handle(request):
        assert request.url.path == "/user/repos"
        assert request.headers["Authorization"] == "Bearer synthetic-read-token"
        assert request.url.params["affiliation"] == "owner,collaborator,organization_member"
        page = int(request.url.params["page"])
        seen.append(page)
        rows = [github_project(page * 100 + index, f"team/other-{index}") for index in range(100)]
        return httpx.Response(200, json=rows if page < 7 else [github_project(700, "team/Needle")])

    real_client = httpx.Client
    with patch("core.git_sources.httpx.Client", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)):
        endpoint = f"/api/git-connections/{connection.pk}/projects"
        first = client.get(endpoint, {"search": "  NEEDLE  ", "page_size": 100}).json()
        assert first["items"] == [] and first["has_more"]
        assert first["page"] == 5 and first["next_page"] == 6
        second = client.get(endpoint, {"search": "NEEDLE", "page_size": 100, "page": first["next_page"]}).json()
    assert seen == list(range(1, 8))
    assert [row["path"] for row in second["items"]] == ["team/Needle"]
    assert second["page"] == 7 and not second["has_more"] and second["next_page"] is None


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_tag_lookup_cannot_silently_select_a_branch_with_the_same_name(provider):
    base = "https://github.com" if provider == "github" else "https://gitlab.example.test"
    connection = GitConnection.objects.create(provider=provider, base_url=base, secret=encrypt("synthetic-token"))
    reader = Provider(connection)
    project = (github_project(42, "team/app") if provider == "github" else
               {"id": 42, "name": "app", "path_with_namespace": "team/app", "http_url_to_repo": base + "/team/app.git"})
    source = reader._record(project)
    seen = []

    def get(path, params=None):
        seen.append(path)
        if path.endswith("/tags"):
            return [{"name": "release", "commit": {"sha": "a" * 40, "id": "a" * 40}}]
        if "/git/ref/tags/" in path:
            return {"ref": "refs/tags/release", "object": {"type": "tag", "sha": "a" * 40}}
        return {"name": "release", "commit": {"sha": "a" * 40 if "/tags/" in path else "b" * 40}}

    with patch.object(reader, "get", side_effect=get):
        tags, more = reader.branches(source, "release", kind="tag")
        assert tags[0]["ref"] == "tag:release" and tags[0]["kind"] == "tag" and not more
        tag = reader.branch(source, tags[0]["ref"])
        branch = reader.branch(source, "release")
    assert branch["commit"]["sha"] == "b" * 40
    assert (tag.get("object") or tag["commit"])["sha"] == "a" * 40
    assert "/tags" in seen[0] and "/branches/" in seen[-1]


def test_namespace_search_uses_the_project_keyword_and_preserves_the_full_path_filter():
    connection = GitConnection.objects.create(provider="gitlab", base_url="https://gitlab.example.test", secret=encrypt("synthetic-token"))
    reader = Provider(connection)
    rows = [{"id": number, "name": "needle", "path_with_namespace": group + "/needle",
             "http_url_to_repo": reader.base + "/" + group + "/needle.git"}
            for number, group in [(1, "other"), (2, "expected")]]
    with patch.object(reader, "get", return_value=rows) as get:
        items, _ = reader.projects("expected/needle")
    assert get.call_args.args[1]["search"] == "needle"
    assert [row["path"] for row in items] == ["expected/needle"]
