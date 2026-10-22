"""Read-only Git provider discovery with credentials pinned to a configured instance."""

import hashlib
import re
import time
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx
from django.utils import timezone
from ninja.errors import HttpError

from .models import EnvironmentRepository, GitConnection, GitRepository
from .secrets import decrypt


class SourceError(ValueError):
    pass


def base_url(provider, value):
    try:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or any(c.isspace() or ord(c) < 32 for c in value)
            or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
        ):
            raise ValueError
        parsed.port
    except ValueError as exc:
        raise HttpError(
            422, "Enter a valid Git server URL without credentials or query parameters."
        ) from exc
    result = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
    )
    if provider == "github" and result != "https://github.com":
        raise HttpError(422, "GitHub source connections use https://github.com.")
    return result


def connection_dict(value):
    references = set(
        value.repositories.filter(environment_repositories__isnull=False).values_list(
            "environment_repositories__environment_id", flat=True
        )
    )
    if value.legacy_source:
        references.update(
            EnvironmentRepository.objects.filter(git_repository__isnull=True).values_list(
                "environment_id", flat=True
            )
        )
    return {
        "id": value.id,
        "name": value.name,
        "provider": value.provider,
        "base_url": value.base_url,
        "account": value.account,
        "enabled": value.enabled,
        "status": value.status,
        "error": value.error,
        "has_secret": bool(value.secret),
        "checked_at": value.checked_at,
        "legacy_source": value.legacy_source,
        "referenced_environments": len(references),
    }


def canonical(source, branch=""):
    digest = hashlib.sha256(source.instance.encode()).hexdigest()[:16]
    suffix = "-" + hashlib.sha256(branch.encode()).hexdigest()[:16] if branch else ""
    return f"git-{source.provider}-{digest}/{source.remote_id}{suffix}"


def repository_dict(value):
    return {
        "id": value.remote_id,
        "remote_id": value.remote_id,
        "path": value.path,
        "name": value.name,
        "clone_url": value.clone_url,
        "default_branch": value.default_branch,
        "is_fork": value.is_fork,
        "parent": value.parent,
        "git_repository_id": value.id,
    }


class Provider:
    def __init__(self, connection):
        self.connection = connection
        self.base = base_url(connection.provider, connection.base_url)
        if not connection.enabled:
            raise SourceError("This Git connection is disabled.")
        if not connection.secret:
            raise SourceError("Connect this Git account before browsing its projects.")
        try:
            self.secret = decrypt(connection.secret)
        except Exception as exc:
            raise SourceError("This Git credential cannot be read. Reconnect the account.") from exc
        self.api = (
            "https://api.github.com" if connection.provider == "github" else self.base + "/api/v4"
        )

    def get(self, path, params=None):
        headers = {"Accept": "application/json"}
        headers["Authorization" if self.connection.provider == "github" else "PRIVATE-TOKEN"] = (
            "Bearer " + self.secret if self.connection.provider == "github" else self.secret
        )
        try:
            deadline = time.monotonic() + 45
            with httpx.Client(
                timeout=httpx.Timeout(20, connect=5), follow_redirects=False, trust_env=False
            ) as client:
                with client.stream(
                    "GET", self.api + path, params=params, headers=headers
                ) as response:
                    if response.status_code != 200:
                        if response.status_code in {401, 403}:
                            raise SourceError(
                                "Git access denied: check authentication and read permissions."
                            )
                        if response.status_code == 404:
                            raise SourceError(
                                "The Git project or branch is unavailable to this connection."
                            )
                        raise SourceError("Git discovery failed. Check the server and retry.")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if time.monotonic() > deadline:
                            raise SourceError("Git discovery timed out. Retry shortly.")
                        if len(data) > 2_000_000:
                            raise SourceError("The Git server response is too large.")
                    import json

                    return json.loads(data)
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError("Git discovery failed. Check the server and retry.") from exc

    def test(self):
        data = self.get("/user")
        if not isinstance(data, dict):
            raise SourceError("The Git server returned invalid account metadata.")
        return str(data.get("login") or data.get("username") or data.get("name") or "")[:200]

    def _record(self, data):
        if not isinstance(data, dict):
            raise SourceError("The Git server returned invalid project metadata.")
        github = self.connection.provider == "github"
        remote_id = str(data.get("id", ""))
        path = data.get("full_name" if github else "path_with_namespace", "")
        clone = data.get("clone_url" if github else "http_url_to_repo", "")
        if (
            not re.fullmatch(r"[1-9][0-9]{0,31}", remote_id)
            or not isinstance(path, str)
            or not path
            or len(path) > 500
        ):
            raise SourceError("The Git server returned invalid project metadata.")
        if not isinstance(clone, str) or len(clone) > 1500:
            raise SourceError("The Git server returned an invalid project clone URL.")
        origin = urlsplit(self.base)
        try:
            remote = urlsplit(clone)
        except ValueError as exc:
            raise SourceError("The Git server returned an invalid project clone URL.") from exc
        if (
            remote.scheme != origin.scheme
            or remote.netloc.lower() != origin.netloc.lower()
            or remote.username
            or remote.password
            or remote.query
            or remote.fragment
            or not remote.path.startswith(origin.path.rstrip("/") + "/")
            or any(p in {".", ".."} for p in unquote(remote.path).split("/"))
            or "\\" in clone
            or any(c.isspace() or ord(c) < 32 for c in clone)
        ):
            raise SourceError("The project clone URL does not belong to this Git instance.")
        expected_path = origin.path.rstrip("/") + "/" + path
        actual_path = unquote(remote.path)
        if actual_path not in {expected_path, expected_path + ".git"}:
            raise SourceError("The project clone URL does not match the selected repository.")
        parent = data.get("parent" if github else "forked_from_project") or {}
        if not isinstance(parent, dict):
            parent = {}
        parent_value = (
            {
                "path": str(parent.get("full_name" if github else "path_with_namespace", ""))[:500],
                "url": str(parent.get("html_url" if github else "web_url", ""))[:1500],
            }
            if parent
            else {}
        )
        value, _ = GitRepository.objects.update_or_create(
            connection=self.connection,
            remote_id=remote_id,
            defaults={
                "provider": self.connection.provider,
                "instance": self.base,
                "path": path[:500],
                "name": str(data.get("name") or path)[:255],
                "clone_url": clone,
                "default_branch": str(data.get("default_branch") or "")[:255],
                "is_fork": bool(data.get("fork") if github else parent),
                "parent": parent_value,
            },
        )
        return value

    def projects(self, search="", page=1, page_size=30):
        params = {"per_page": page_size, "page": page}
        if self.connection.provider == "github":
            data = self.get(
                "/user/repos",
                {
                    **params,
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "full_name",
                },
            )
        else:
            data = self.get(
                "/projects",
                {
                    **params,
                    "membership": "true",
                    "search": search,
                    "order_by": "path",
                    "sort": "asc",
                },
            )
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise SourceError("The Git server returned invalid project metadata.")
        return [
            repository_dict(self._record(item))
            for item in data
            if search.casefold()
            in str(
                item.get(
                    "full_name" if self.connection.provider == "github" else "path_with_namespace",
                    "",
                )
            ).casefold()
        ], len(data) == page_size

    def project(self, remote_id):
        if not re.fullmatch(r"[1-9][0-9]{0,31}", str(remote_id)):
            raise SourceError("Select a valid remote project identifier.")
        path = (
            "/repositories/" + str(remote_id)
            if self.connection.provider == "github"
            else "/projects/" + str(remote_id)
        )
        source = self._record(self.get(path))
        if source.remote_id != str(remote_id):
            raise SourceError("The Git server returned a different project identifier.")
        return source

    def branches(self, source, search="", page=1, page_size=30):
        params = {"per_page": page_size, "page": page}
        if self.connection.provider == "github":
            path = (
                "/repos/"
                + "/".join(quote(p, safe="") for p in source.path.split("/"))
                + "/branches"
            )
        else:
            path = "/projects/" + source.remote_id + "/repository/branches"
            if search:
                params["search"] = search
        data = self.get(path, params)
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise SourceError("The Git server returned invalid branch metadata.")
        return [
            {
                "name": item["name"],
                "sha": item.get("commit", {}).get("sha") or item.get("commit", {}).get("id", ""),
                "protected": bool(item.get("protected")),
            }
            for item in data
            if isinstance(item.get("name"), str) and search.casefold() in item["name"].casefold()
        ], len(data) == page_size

    def branch(self, source, branch):
        if self.connection.provider == "github":
            path = (
                "/repos/"
                + "/".join(quote(p, safe="") for p in source.path.split("/"))
                + "/branches/"
            )
        else:
            path = "/projects/" + source.remote_id + "/repository/branches/"
        data = self.get(path + quote(branch, safe=""))
        if not isinstance(data, dict) or data.get("name") != branch:
            raise SourceError("The selected Git branch is unavailable.")
        return data


def fail_connection(connection, error):
    GitConnection.objects.filter(pk=connection.pk).update(
        status="ERROR", error=str(error), checked_at=timezone.now()
    )


def normalize_selection(selection):
    object.__setattr__(selection, "git_repository_id", None)
    connection_id = getattr(selection, "git_connection_id", None)
    if not connection_id:
        return None
    try:
        connection = GitConnection.objects.get(pk=connection_id)
        provider = Provider(connection)
        source = provider.project(selection.remote_id)
        provider.branch(source, selection.branch)
    except GitConnection.DoesNotExist as exc:
        raise HttpError(422, "Select an existing Git connection.") from exc
    except SourceError as exc:
        fail_connection(connection, exc)
        raise HttpError(422, str(exc)) from exc
    selection.repository = canonical(source, selection.branch)
    object.__setattr__(selection, "git_repository_id", source.id)
    return source


def repository_snapshot(repo):
    result = {"repository": repo.repository, "branch": repo.branch, "sha": repo.sha}
    if repo.git_repository_id:
        source = repo.git_repository
        result.update(
            git_repository_id=source.id,
            git_connection_id=source.connection_id,
            connection_name=source.connection.name,
            provider=source.provider,
            instance=source.instance,
            remote_id=source.remote_id,
            path=source.path,
            is_fork=source.is_fork,
            parent=source.parent,
        )
    return result
