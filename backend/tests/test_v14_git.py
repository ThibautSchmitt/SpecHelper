"""Mixed source identities share mirrors while retaining frozen request worktrees."""

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.git import mirror_path, request_workspace, sync_environment
from core.git_sources import canonical, repository_snapshot
from core.models import (
    Environment,
    EnvironmentRepository,
    GitConnection,
    GitRepository,
    Request,
)
from core.secrets import encrypt

pytestmark = pytest.mark.django_db


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def source(connection, remote_id, path, fork=False):
    return GitRepository.objects.create(
        connection=connection,
        provider=connection.provider,
        instance=connection.base_url,
        remote_id=remote_id,
        path=path,
        name=path.split("/")[-1],
        clone_url=connection.base_url + "/" + path + ".git",
        is_fork=fork,
        parent={"path": "upstream/parent"} if fork else {},
    )


def test_three_mixed_sources_fork_and_shared_account_mirror_keep_old_shas(storage):
    github = GitConnection.objects.create(
        name="GitHub",
        provider="github",
        base_url="https://github.com",
        secret=encrypt("fixture-gh"),
    )
    gitlab = GitConnection.objects.create(
        name="GitLab",
        provider="gitlab",
        base_url="https://gitlab.example",
        secret=encrypt("fixture-gl"),
    )
    sources = [
        source(github, "101", "company/backend"),
        source(gitlab, "202", "team/frontend"),
        source(gitlab, "303", "user/fork", True),
    ]
    local = storage / "source"
    local.mkdir()
    git(local, "init", "-b", "main")
    git(local, "config", "user.name", "Fixture")
    git(local, "config", "user.email", "fixture@example.invalid")
    shas = {}
    for index, branch in enumerate(["main", "release", "fork-feature"]):
        if index:
            git(local, "checkout", "-b", branch)
        (local / "source.txt").write_text(branch)
        git(local, "add", ".")
        git(local, "commit", "-m", branch)
        shas[branch] = git(local, "rev-parse", "HEAD")
    for entry in sources:
        mirror = mirror_path(SimpleNamespace(git_repository_id=entry.pk, git_repository=entry))
        mirror.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--mirror", str(local), str(mirror)], check=True, capture_output=True
        )
    env = Environment.objects.create(name="Mixed")
    for entry, branch in zip(sources, shas, strict=True):
        EnvironmentRepository.objects.create(
            environment=env,
            repository=canonical(entry, branch),
            git_repository=entry,
            branch=branch,
        )
    with patch("core.git.fetch", side_effect=mirror_path):
        sync_environment(env.pk)
    env.refresh_from_db()
    assert env.status == "READY"
    request = Request.objects.create(
        environment=env,
        need="Mixed sources",
        baseline=[repository_snapshot(repo) for repo in env.repositories.all()],
    )
    assert {item["provider"] for item in request.baseline} == {"github", "gitlab"}
    fork = next(item for item in request.baseline if item["is_fork"])
    assert fork["remote_id"] == "303" and fork["path"] == "user/fork"
    frozen = request_workspace(request)
    for item in request.baseline:
        assert (frozen / item["repository"] / "source.txt").read_text() == item["branch"]
    old_workspaces = {repo.repository: repo.workspace for repo in env.repositories.all()}
    (local / "source.txt").write_text("new fork")
    git(local, "commit", "-am", "new fork")
    fork_source = sources[-1]
    git(
        mirror_path(SimpleNamespace(git_repository_id=fork_source.pk, git_repository=fork_source)),
        "fetch",
        "origin",
    )
    with patch("core.git.fetch", side_effect=mirror_path):
        sync_environment(env.pk)
    request.refresh_from_db()
    assert request.baseline[-1]["sha"] == shas["fork-feature"]
    assert (
        request_workspace(request) / fork["repository"] / "source.txt"
    ).read_text() == "fork-feature"
    current = env.repositories.get(git_repository=fork_source)
    assert (
        git(mirror_path(current), "rev-parse", "refs/spechelper/retained/" + fork["sha"])
        == fork["sha"]
    )
    assert current.sha != fork["sha"] and current.workspace != old_workspaces[current.repository]
    duplicate_account = GitConnection.objects.create(
        name="Second account", provider="gitlab", base_url=gitlab.base_url, secret=encrypt("other")
    )
    duplicate = source(duplicate_account, fork_source.remote_id, fork_source.path, True)
    assert mirror_path(
        SimpleNamespace(git_repository_id=duplicate.pk, git_repository=duplicate)
    ) == mirror_path(current)
    assert len(list((storage / "git-cache").rglob("*.git"))) == 3


def test_same_remote_different_branches_use_distinct_selection_paths(storage):
    conn = GitConnection.objects.create(
        name="Sources", provider="gitlab", base_url="https://gitlab.example"
    )
    entry = source(conn, "1", "team/repo")
    assert canonical(entry, "main") != canonical(entry, "release")
    assert mirror_path(
        SimpleNamespace(git_repository_id=entry.pk, git_repository=entry)
    ) == mirror_path(SimpleNamespace(git_repository_id=entry.pk, git_repository=entry))
    local = storage / "source"
    local.mkdir()
    git(local, "init", "-b", "main")
    git(local, "config", "user.name", "Fixture")
    git(local, "config", "user.email", "fixture@example.invalid")
    (local / "branch.txt").write_text("main")
    git(local, "add", ".")
    git(local, "commit", "-m", "main")
    git(local, "checkout", "-b", "release")
    (local / "branch.txt").write_text("release")
    git(local, "commit", "-am", "release")
    mirror = mirror_path(SimpleNamespace(git_repository_id=entry.pk, git_repository=entry))
    mirror.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--mirror", str(local), str(mirror)], check=True, capture_output=True
    )
    env = Environment.objects.create(name="Two branches")
    for branch in ("main", "release"):
        EnvironmentRepository.objects.create(
            environment=env,
            repository=canonical(entry, branch),
            git_repository=entry,
            branch=branch,
        )
    with patch("core.git.fetch", side_effect=mirror_path):
        sync_environment(env.pk)
        sync_environment(env.pk)
    for repo in env.repositories.all():
        from pathlib import Path

        assert (Path(repo.workspace) / "branch.txt").read_text() == repo.branch
    from core.git import lock

    with lock(canonical(entry, "main")):
        with pytest.raises(BlockingIOError):
            with lock(canonical(entry, "release"), blocking=False):
                pass
    from core.environments import delete

    delete(env.pk, SimpleNamespace(expected_revision=env.revision, confirm_name=env.name))
    assert not Environment.objects.filter(pk=env.pk).exists()
