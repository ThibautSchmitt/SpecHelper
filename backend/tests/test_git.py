import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.git import materialize, mirror_path, request_workspace, sync_environment
from core.models import AIConnection, Environment, EnvironmentRepository, Request
from core.services import enqueue_analysis

pytestmark = pytest.mark.django_db


def test_repository_paths_are_unambiguous(storage):
    assert mirror_path("a--b/c") != mirror_path("a/b--c")
    assert mirror_path("Company/Project") == mirror_path("company/project")


def git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def test_mirror_shared_between_branches_and_request_baseline_immutable(storage):
    AIConnection.objects.update_or_create(
        pk=1, defaults={"agent": "codex", "status": "CONNECTED", "availability": "AVAILABLE"}
    )
    source = storage / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Test")
    (source / "domain.txt").write_text("production")
    git(source, "add", ".")
    git(source, "commit", "-m", "production")
    main_sha = git(source, "rev-parse", "HEAD")
    git(source, "checkout", "-b", "develop")
    (source / "domain.txt").write_text("preproduction")
    git(source, "commit", "-am", "preproduction")
    develop_sha = git(source, "rev-parse", "HEAD")
    mirror = mirror_path("company/project")
    mirror.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--mirror", str(source), str(mirror)], check=True, capture_output=True
    )
    prod = Environment.objects.create(name="Production")
    preprod = Environment.objects.create(name="Staging")
    for env, branch in [(prod, "main"), (preprod, "develop")]:
        EnvironmentRepository.objects.create(
            environment=env, repository="company/project", branch=branch
        )
    with patch("core.git.fetch", return_value=mirror):
        sync_environment(prod.id)
        sync_environment(preprod.id)
    prod.refresh_from_db()
    assert prod.status == "READY"
    assert prod.repositories.get().sha == main_sha
    assert preprod.repositories.get().sha == develop_sha
    assert len(list((storage / "git-cache").rglob("*.git"))) == 1
    request = Request.objects.create(environment=preprod, need="Domain change")
    request = enqueue_analysis(request.id)
    workspace = request_workspace(request)
    assert (workspace / "company/project" / "domain.txt").read_text() == "preproduction"
    (source / "domain.txt").write_text("newer")
    git(source, "commit", "-am", "newer")
    git(mirror, "fetch", "origin")
    with patch("core.git.fetch", return_value=mirror):
        sync_environment(preprod.id)
    assert preprod.repositories.get().sha != develop_sha
    request.refresh_from_db()
    assert request.baseline[0]["sha"] == develop_sha
    assert (
        request_workspace(request) / "company/project" / "domain.txt"
    ).read_text() == "preproduction"
    assert Path(prod.repositories.get().workspace, "domain.txt").read_text() == "production"
    from core.environments import delete, update
    from core.models import Job

    retained = preprod.repositories.get()
    before_inode = Path(retained.workspace, ".git").stat().st_ino
    updated = update(
        preprod.id,
        SimpleNamespace(
            name="Renamed validation environment",
            database_id=None,
            expected_revision=1,
            repositories=[SimpleNamespace(repository="company/project", branch="develop")],
        ),
    )
    job = Job.objects.get(kind="sync")
    assert job.payload["changed_repositories"] == []
    with patch("core.git.fetch") as fetched:
        sync_environment(updated.id, job.payload["changed_repositories"])
    fetched.assert_not_called()
    assert Path(retained.workspace, ".git").stat().st_ino == before_inode
    legacy = storage / "environments" / str(updated.id) / develop_sha / "company/project"
    materialize(mirror, legacy, develop_sha)
    delete(updated.id, SimpleNamespace(confirm_name=updated.name, expected_revision=2))
    request.refresh_from_db()
    assert request.environment_id is None
    assert request.environment_name_snapshot == "Staging"
    assert (
        request_workspace(request) / "company/project/domain.txt"
    ).read_text() == "preproduction"
    assert not (storage / "environments" / str(updated.id)).exists()
    assert Path(prod.repositories.get().workspace, "domain.txt").read_text() == "production"
    assert mirror.exists()
    assert str(storage / "environments" / str(updated.id)) not in git(
        mirror, "worktree", "list", "--porcelain"
    )
