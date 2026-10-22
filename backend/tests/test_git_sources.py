"""Read-only discovery against independent local GitLab-compatible HTTP servers."""

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from ninja.errors import HttpError

from core.git_source_api import ConnectionIn, create, delete, update
from core.git_sources import Provider, SourceError, base_url, normalize_selection
from core.models import Environment, EnvironmentRepository, GitConnection, Request
from core.secrets import decrypt, encrypt

pytestmark = pytest.mark.django_db


@contextmanager
def server(token, project_id=17, redirect=False):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("PRIVATE-TOKEN")))
            if redirect:
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:1/leak")
                self.end_headers()
                return
            if self.headers.get("PRIVATE-TOKEN") != token:
                self.send_response(401)
                self.end_headers()
                return
            origin = f"http://127.0.0.1:{self.server.server_port}"
            project = {
                "id": project_id,
                "path_with_namespace": "team/fork",
                "name": "fork",
                "http_url_to_repo": origin + "/team/fork.git",
                "default_branch": "main",
                "forked_from_project": {
                    "path_with_namespace": "upstream/parent",
                    "web_url": origin + "/upstream/parent",
                },
            }
            if "/repository/branches" in self.path:
                branch = {"name": "feature/a", "commit": {"id": "a" * 40}, "protected": False}
                data = branch if self.path.split("?")[0].endswith("feature%2Fa") else [branch]
            elif self.path.startswith("/api/v4/user"):
                data = {"username": "reader"}
            elif self.path.split("?")[0] == "/api/v4/projects":
                data = [project]
            else:
                data = project
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", seen
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def connection(origin, token, name="GitLab"):
    return GitConnection.objects.create(
        name=name, provider="gitlab", base_url=origin, secret=encrypt(token)
    )


def test_independent_gitlab_servers_discover_projects_forks_branches(storage, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    with server("reader-one") as (url1, seen1), server("reader-two", 29) as (url2, seen2):
        first, second = connection(url1, "reader-one"), connection(url2, "reader-two")
        for conn, expected in [(first, "17"), (second, "29")]:
            provider = Provider(conn)
            assert provider.test() == "reader"
            items, more = provider.projects("fork", 1, 1)
            assert more and items[0]["remote_id"] == expected
            assert items[0]["is_fork"] and items[0]["parent"]["path"] == "upstream/parent"
            source = provider.project(expected)
            branches, _ = provider.branches(source, "feature")
            assert branches[0]["name"] == "feature/a"
            assert provider.branch(source, "feature/a")["name"] == "feature/a"
            selection = SimpleNamespace(
                git_connection_id=conn.pk, remote_id=expected, branch="feature/a"
            )
            normalize_selection(selection)
            assert selection.git_repository_id == source.pk
        assert all(secret == "reader-one" for _, secret in seen1)
        assert all(secret == "reader-two" for _, secret in seen2)
        assert "%2F" in seen1[-1][0]


def test_redirects_never_follow_or_forward_credentials(storage):
    with server("reader", redirect=True) as (origin, seen):
        conn = connection(origin, "reader")
        with pytest.raises(SourceError, match="discovery failed"):
            Provider(conn).test()
        assert len(seen) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://u:p@gitlab.example",
        "https://gitlab.example?q=secret",
        "https://gitlab.example/%2e%2e/escape",
        "file:///tmp/repo",
    ],
)
def test_instance_url_rejects_credential_and_traversal(url):
    with pytest.raises(HttpError):
        base_url("gitlab", url)


def test_secret_preserving_update_and_historical_delete_protection(storage):
    row = create(
        None,
        ConnectionIn(
            name="Personal",
            provider="gitlab",
            base_url="https://gitlab.com",
            secret="fixture-read-only",
        ),
    )
    conn = GitConnection.objects.get(pk=row["id"])
    assert row["has_secret"] and "secret" not in row and decrypt(conn.secret) == "fixture-read-only"
    update(
        None,
        conn.pk,
        ConnectionIn(name="Renamed", provider="gitlab", base_url="https://gitlab.com"),
    )
    conn.refresh_from_db()
    assert decrypt(conn.secret) == "fixture-read-only"
    from core.models import GitRepository

    source = GitRepository.objects.create(
        connection=conn,
        provider="gitlab",
        instance=conn.base_url,
        remote_id="12",
        path="team/repo",
        name="repo",
        clone_url=conn.base_url + "/team/repo.git",
    )
    request = Request.objects.create(
        need="Historical", baseline=[{"git_repository_id": source.pk, "sha": "a" * 40}]
    )
    with pytest.raises(HttpError) as error:
        delete(None, conn.pk)
    assert error.value.status_code == 409
    assert delete(None, conn.pk, "Renamed")["status"] == "DISABLED"
    conn.refresh_from_db()
    request.refresh_from_db()
    assert not conn.enabled and request.baseline[0]["sha"] == "a" * 40


def test_forged_clone_origin_is_rejected_without_parent_substitution(storage):
    conn = connection("https://gitlab.com", "reader")
    provider = Provider(conn)
    with pytest.raises(SourceError, match="clone URL"):
        provider._record(
            {
                "id": 1,
                "path_with_namespace": "user/fork",
                "http_url_to_repo": "https://evil.invalid/repo.git",
            }
        )


def test_invalid_auth_marks_connection_without_deleting_environment(storage):
    conn = connection("https://gitlab.com", "reader")
    env = Environment.objects.create(name="Existing")
    EnvironmentRepository.objects.create(environment=env, repository="team/repo", branch="main")
    selection = SimpleNamespace(git_connection_id=conn.pk, remote_id="17", branch="main")
    with patch.object(
        Provider,
        "project",
        side_effect=SourceError("Git access denied: check authentication and read permissions."),
    ):
        with pytest.raises(HttpError):
            normalize_selection(selection)
    conn.refresh_from_db()
    assert conn.status == "ERROR" and Environment.objects.filter(pk=env.pk).exists()


def test_legacy_connection_disable_and_history_are_honored(storage):
    from core.git import source_token

    conn = GitConnection.objects.create(
        name="Imported GitHub",
        provider="github",
        base_url="https://github.com",
        legacy_source=True,
        secret=encrypt("read-sources-only"),
    )
    assert source_token(None) == "read-sources-only"
    env = Environment.objects.create(name="Legacy")
    EnvironmentRepository.objects.create(environment=env, repository="company/repo", branch="main")
    with pytest.raises(HttpError):
        delete(None, conn.pk)
    assert delete(None, conn.pk, conn.name)["status"] == "DISABLED"
    with pytest.raises(SourceError, match="disabled"):
        source_token(None)
    assert Environment.objects.filter(pk=env.pk).exists()


def test_github_api_headers_pagination_and_fork_metadata(storage):
    import httpx

    conn = GitConnection.objects.create(
        name="GitHub", provider="github", base_url="https://github.com", secret=encrypt("read-gh")
    )
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer read-gh"
        assert request.url.host == "api.github.com"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 42,
                    "full_name": "member/fork",
                    "name": "fork",
                    "clone_url": "https://github.com/member/fork.git",
                    "fork": True,
                    "parent": {
                        "full_name": "upstream/parent",
                        "html_url": "https://github.com/upstream/parent",
                    },
                }
            ],
        )

    real_client = httpx.Client
    with patch(
        "core.git_sources.httpx.Client",
        side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    ):
        result, more = Provider(conn).projects("fork", page=2, page_size=1)
    assert result[0]["remote_id"] == "42" and result[0]["is_fork"] and more
    assert seen[0].url.params["page"] == "2"
    assert "affiliation" in seen[0].url.params


def test_selection_ignores_client_injected_internal_repository_id():
    selection = SimpleNamespace(
        git_connection_id=None, git_repository_id=999, repository="legacy/repo", branch="main"
    )
    assert normalize_selection(selection) is None and selection.git_repository_id is None


@pytest.mark.parametrize(
    "clone",
    [
        "https://gitlab.com/team/a repo.git",
        "https://gitlab.com/team/repo\n.git",
        "https://gitlab.com/team/\\repo.git",
    ],
)
def test_clone_urls_with_whitespace_or_backslashes_are_rejected(storage, clone):
    conn = connection("https://gitlab.com", "reader")
    with pytest.raises(SourceError, match="clone URL"):
        Provider(conn)._record(
            {"id": 1, "path_with_namespace": "team/repo", "http_url_to_repo": clone}
        )


@pytest.mark.parametrize("remote_id", [None, True, -1, "1" * 256])
def test_malformed_remote_ids_are_rejected(storage, remote_id):
    conn = connection("https://gitlab.com", "reader")
    with pytest.raises(SourceError, match="metadata"):
        Provider(conn)._record(
            {
                "id": remote_id,
                "path_with_namespace": "team/repo",
                "http_url_to_repo": "https://gitlab.com/team/repo.git",
            }
        )


def test_oversized_remote_path_is_rejected_instead_of_truncated(storage):
    conn = connection("https://gitlab.com", "reader")
    with pytest.raises(SourceError, match="metadata"):
        Provider(conn)._record(
            {
                "id": 1,
                "path_with_namespace": "team/" + "r" * 500,
                "http_url_to_repo": "https://gitlab.com/team/repo.git",
            }
        )


def test_fork_clone_cannot_silently_use_parent_same_origin(storage):
    conn = connection("https://gitlab.com", "reader")
    with pytest.raises(SourceError, match="selected repository"):
        Provider(conn)._record(
            {
                "id": 1,
                "path_with_namespace": "member/fork",
                "http_url_to_repo": "https://gitlab.com/upstream/parent.git",
                "forked_from_project": {"path_with_namespace": "upstream/parent"},
            }
        )


def test_provider_cannot_replace_selected_remote_identifier(storage):
    conn = connection("https://gitlab.com", "reader")
    with patch.object(
        Provider,
        "get",
        return_value={
            "id": 2,
            "path_with_namespace": "team/repo",
            "http_url_to_repo": "https://gitlab.com/team/repo.git",
        },
    ):
        with pytest.raises(SourceError, match="different project identifier"):
            Provider(conn).project("1")


def test_legacy_input_cannot_forge_new_source_identifier(storage):
    from core.environments import validate

    payload = SimpleNamespace(
        name="Spoof",
        database_id=None,
        repositories=[
            SimpleNamespace(
                repository="git-gitlab-0123456789abcdef/17-0123456789abcdef", branch="main"
            )
        ],
    )
    with pytest.raises(HttpError, match="Git connection"):
        validate(payload)


@pytest.mark.parametrize("status", ["CONNECTED", "ERROR", "EXPIRED", "CANCELLED"])
def test_completed_browser_attempt_does_not_prevent_unreferenced_source_deletion(storage, status):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import ConnectionAttempt, GitHubConnection

    original = GitHubConnection.objects.create(
        pk=1, secret=encrypt("publication-only"), account="Publisher", status="CONNECTED"
    )
    conn = GitConnection.objects.create(
        name="Disposable source",
        provider="github",
        base_url="https://github.com",
        secret=encrypt("read-only"),
    )
    attempt = ConnectionAttempt.objects.create(
        provider="github",
        git_connection=conn,
        status=status,
        expires_at=timezone.now() + timedelta(minutes=1),
    )
    assert delete(None, conn.pk)["status"] == "DELETED"
    attempt.refresh_from_db()
    original.refresh_from_db()
    assert attempt.git_connection_id is None and attempt.status == status
    assert original.account == "Publisher" and decrypt(original.secret) == "publication-only"
    assert not GitConnection.objects.filter(pk=conn.pk).exists()


@pytest.mark.parametrize("status", ["STARTING", "AWAITING_USER"])
def test_active_browser_attempt_requires_explicit_cancellation_before_delete(storage, status):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import ConnectionAttempt

    conn = GitConnection.objects.create(
        name="Pending source", provider="github", base_url="https://github.com"
    )
    attempt = ConnectionAttempt.objects.create(
        provider="github",
        git_connection=conn,
        status=status,
        expires_at=timezone.now() + timedelta(minutes=1),
    )
    with pytest.raises(HttpError, match="Cancel the active") as error:
        delete(None, conn.pk)
    assert error.value.status_code == 409
    attempt.refresh_from_db()
    assert attempt.git_connection_id == conn.pk and attempt.status == status
    assert GitConnection.objects.filter(pk=conn.pk).exists()


@pytest.mark.parametrize("status", ["STARTING", "AWAITING_USER"])
def test_expired_active_browser_attempt_is_cancelled_before_target_is_detached(storage, status):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import ConnectionAttempt, GitHubConnection

    original = GitHubConnection.objects.create(pk=1, secret=encrypt("unchanged"))
    conn = GitConnection.objects.create(
        name="Expired source", provider="github", base_url="https://github.com"
    )
    attempt = ConnectionAttempt.objects.create(
        provider="github",
        git_connection=conn,
        status=status,
        input_required=True,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    assert delete(None, conn.pk)["status"] == "DELETED"
    attempt.refresh_from_db()
    original.refresh_from_db()
    assert attempt.status == "CANCELLED" and attempt.git_connection_id is None
    assert not attempt.input_required and decrypt(original.secret) == "unchanged"
