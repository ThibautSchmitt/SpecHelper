import json
import subprocess
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from core import branch_checks
from core.git import mirror_path, request_workspace, sync_environment
from core.models import (
    Environment,
    EnvironmentRepository,
    GeneratedArtifact,
    Job,
    Request,
    ResultVersion,
)
from core.worker import claim_job, perform_job, recover_stale_jobs

pytestmark = pytest.mark.django_db


def git(cwd, *args):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


@pytest.fixture
def remote(storage):
    source = storage / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.invalid")
    git(source, "config", "user.name", "Test")
    (source / "source.txt").write_text("first")
    git(source, "add", ".")
    git(source, "commit", "-m", "first")
    mirror = mirror_path("company/backend")
    mirror.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--mirror", str(source), str(mirror)], check=True, capture_output=True
    )
    return source, mirror


def refresh(mirror):
    def fetch(*args, **kwargs):
        source = git(mirror, "config", "--get", "remote.origin.url")
        git(mirror, "fetch", "--prune", source, "+refs/heads/*:refs/heads/*")
        return mirror

    return fetch


def advance(source, message):
    (source / "source.txt").write_text(message)
    git(source, "commit", "-am", message)
    return git(source, "rev-parse", "HEAD")


def test_real_remote_counts_and_selective_sync_preserve_analysis(storage, remote, client):
    source, mirror = remote
    environment = Environment.objects.create(name="Two branches", status="READY")
    original = git(source, "rev-parse", "HEAD")
    repo = EnvironmentRepository.objects.create(
        environment=environment, repository="company/backend", branch="main", sha=original
    )
    git(source, "branch", "stable")
    other = EnvironmentRepository.objects.create(
        environment=environment, repository="company/frontend", branch="stable", sha=original
    )
    # Independent physical mirrors can point at the same local test remote.
    second_mirror = mirror_path(other.repository)
    subprocess.run(
        ["git", "clone", "--mirror", str(source), str(second_mirror)],
        check=True,
        capture_output=True,
    )
    request = Request.objects.create(
        environment=environment,
        need="Explain",
        baseline=[{"repository": repo.repository, "sha": original}],
    )
    analysis_workspace = request_workspace(request)
    original_content = (analysis_workspace / repo.repository / "source.txt").read_text()
    version = ResultVersion.objects.create(request=request, number=1, baseline=request.baseline)
    proof = GeneratedArtifact.objects.create(version=version, name="goal.md", content="Frozen source: " + original)
    advance(source, "second")
    latest = advance(source, "third")

    def fetch(repository, **kwargs):
        target = mirror_path(repository)
        return refresh(target)()

    with patch("core.git.fetch", side_effect=fetch):
        branch_checks.check_environment(environment.pk)
    repo.refresh_from_db()
    assert repo.sha == original
    assert repo.synced_at is None
    last_checked = repo.git_status["checked_at"]
    assert branch_checks.last_successful_check(repo) == last_checked
    assert branch_checks.describe(repo)["behind"] == 2
    assert branch_checks.summary(environment.repositories.all()) == "PARTIAL"
    assert branch_checks.describe(environment.repositories.get(pk=other.pk))["status"] == "CURRENT"
    data = client.get("/api/environments").json()[0]
    assert data["git_sync_status"] == "PARTIAL"
    assert data["repositories"][0]["git_status"]["behind"] == 2
    assert data["repositories"][0]["last_checked_at"] == last_checked
    assert data["repositories"][0]["synced_at"] is None
    response = client.post(
        f"/api/environments/{environment.pk}/repositories/{repo.pk}/sync",
        data=json.dumps({"expected_revision": 1}),
        content_type="application/json",
    )
    assert response.status_code == 200
    job = Job.objects.get(kind="sync")
    assert job.payload["changed_repositories"] == [repo.repository]
    with patch("core.git.fetch", side_effect=fetch) as fetched:
        sync_environment(environment.pk, job.payload["changed_repositories"])
    assert fetched.call_count == 1
    repo.refresh_from_db()
    other.refresh_from_db()
    request.refresh_from_db()
    assert repo.sha == latest
    assert repo.synced_at is not None
    assert other.sha == original
    assert other.synced_at is None
    assert request.baseline[0]["sha"] == original
    assert (analysis_workspace / repo.repository / "source.txt").read_text() == original_content
    version.refresh_from_db()
    proof.refresh_from_db()
    assert version.baseline[0]["sha"] == original
    assert proof.content == "Frozen source: " + original
    assert branch_checks.summary(environment.repositories.all()) == "SYNCED"
    advance(source, "fourth")
    git(source, "checkout", "stable")
    advance(source, "stable second")
    job.status = "DONE"
    job.save()
    with patch("core.git.fetch", side_effect=fetch):
        branch_checks.check_environment(environment.pk)
    assert branch_checks.summary(environment.repositories.all()) == "OUTDATED"


def test_force_push_deleted_branch_and_failed_fetch_are_not_current(environment, remote):
    source, mirror = remote
    old = advance(source, "second")
    git(mirror, "fetch", "origin")
    repo = environment.repositories.get()
    repo.sha = old
    repo.save()
    git(source, "reset", "--hard", "HEAD~1")
    advance(source, "replacement")
    with patch("core.git.fetch", side_effect=refresh(mirror)):
        branch_checks.check_environment(environment.pk)
    repo.refresh_from_db()
    assert repo.git_status["status"] == "DIVERGED"
    assert repo.git_status["ahead"] == repo.git_status["behind"] == 1
    assert git(mirror, "rev-parse", "refs/spechelper/retained/" + old) == old
    git(source, "checkout", "-b", "replacement")
    git(source, "branch", "-D", "main")
    with patch("core.git.fetch", side_effect=refresh(mirror)):
        branch_checks.check_environment(environment.pk)
    repo.refresh_from_db()
    assert repo.git_status["status"] == "MISSING"
    last_success = branch_checks.last_successful_check(repo)
    assert branch_checks.summary([repo]) == "UNKNOWN"
    with patch("core.git.fetch", side_effect=ValueError("synthetic private token")):
        branch_checks.check_environment(environment.pk)
    repo.refresh_from_db()
    environment.refresh_from_db()
    assert repo.git_status["status"] == "UNAVAILABLE"
    assert branch_checks.last_successful_check(repo) == last_success
    assert branch_checks.summary([repo]) == "UNKNOWN"
    assert "private" not in json.dumps(repo.git_status)
    assert environment.status == "READY"


def test_cached_observation_is_invalid_after_branch_change_or_expiration(environment):
    repo = environment.repositories.get()
    repo.git_status = branch_checks.observation(repo, "CURRENT")
    assert branch_checks.summary([repo]) == "SYNCED"
    repo.branch = "another"
    assert branch_checks.describe(repo) == {"status": "UNKNOWN"}
    repo.git_status = branch_checks.observation(
        repo, "CURRENT", checked_at=(timezone.now() - timedelta(minutes=16)).isoformat()
    )
    assert branch_checks.summary([repo]) == "UNKNOWN"


def test_manual_check_only_queues_a_deduplicated_observation(client, environment):
    environment.status = "READY"
    environment.save()
    repo = environment.repositories.get()
    original = (repo.sha, repo.workspace, repo.synced_at)
    endpoint = f"/api/environments/{environment.pk}/check-updates"
    with patch("core.git.fetch") as fetch:
        assert client.post(endpoint, {"expected_revision":environment.revision + 1}, content_type="application/json").status_code == 409
        assert not Job.objects.exists()
        for _ in range(2):
            response = client.post(endpoint, {"expected_revision":environment.revision}, content_type="application/json")
            assert response.status_code == 200, response.content
        fetch.assert_not_called()
    assert Job.objects.count() == 1
    assert Job.objects.get().kind == "branch_check"
    repo.refresh_from_db()
    environment.refresh_from_db()
    assert environment.status == "READY"
    assert (repo.sha, repo.workspace, repo.synced_at) == original
    Job.objects.create(kind="sync", target=str(environment.pk))
    assert client.post(endpoint, {"expected_revision":environment.revision}, content_type="application/json").status_code == 409
    assert client.post("/api/environments/999999/check-updates", {"expected_revision":1}, content_type="application/json").status_code == 404


def test_successful_check_date_is_not_reused_for_a_different_branch(environment):
    repo = environment.repositories.get()
    repo.git_status = branch_checks.observation(repo, "CURRENT")
    assert branch_checks.last_successful_check(repo)
    repo.branch = "different"
    assert branch_checks.last_successful_check(repo) is None
    repo.git_status = {"branch":repo.branch,"local_sha":repo.sha,"status":"CURRENT","checked_at":"2026-99-01T10:00:00Z"}
    assert branch_checks.last_successful_check(repo) is None


def test_tag_sync_and_checks_use_the_tag_commit_and_keep_the_analysis_baseline(environment, remote):
    from types import SimpleNamespace

    from core import git as source_git

    source, mirror = remote
    first = git(source, "rev-parse", "HEAD")
    git(source, "tag", "-a", "release", "-m", "Published version")
    branch_commit = advance(source, "new main")
    git(source, "branch", "release")
    repo = environment.repositories.get()
    repo.branch = "tag:release"
    repo.sha = ""
    repo.save()
    historical = Request.objects.create(environment=environment, need="Frozen tag", baseline=[{"sha": first}])
    fake_source = SimpleNamespace(clone_url=str(source), provider="github")
    with patch.object(source_git, "source_for", return_value=fake_source), patch.object(source_git, "mirror_path", return_value=mirror), patch.object(source_git, "source_token", return_value=""):
        source_git.sync_environment(environment.pk)
        repo.refresh_from_db()
        assert repo.sha == first and repo.sha != branch_commit
        newer = advance(source, "new tagged version")
        git(source, "tag", "-f", "-a", "release", "-m", "New published version")
        branch_checks.check_environment(environment.pk)
        repo.refresh_from_db()
    assert repo.git_status["remote_sha"] == newer
    assert repo.sha == first
    historical.refresh_from_db()
    assert historical.baseline == [{"sha": first}]
    assert source_git.selection_ref("refs/tags/a-real-branch") == "refs/heads/refs/tags/a-real-branch"


def test_scheduler_is_persistent_deduplicated_and_reuses_one_job(environment):
    from core.queue import snapshot

    branch_checks.schedule_due()
    branch_checks.schedule_due()
    job = Job.objects.get(kind="branch_check")
    assert job.status == "QUEUED"
    assert snapshot() == []
    job.status = "DONE"
    job.save()
    Environment.objects.filter(pk=environment.pk).update(
        next_git_check_at=timezone.now() - timedelta(seconds=1)
    )
    branch_checks.schedule_due()
    job.refresh_from_db()
    assert job.status == "QUEUED"
    assert Job.objects.count() == 1
    Job.objects.create(kind="sync", target=str(environment.pk))
    with patch("core.git.fetch") as fetched:
        branch_checks.check_environment(environment.pk)
    fetched.assert_not_called()


def test_branch_sync_checks_environment_membership_revision_and_duplicate_jobs(client, environment):
    repo = environment.repositories.get()
    other = Environment.objects.create(name="Other")
    foreign = EnvironmentRepository.objects.create(
        environment=other, repository="team/other", branch="main"
    )
    endpoint = f"/api/environments/{environment.pk}/repositories"

    def post(repo_id, revision=1):
        return client.post(
            f"{endpoint}/{repo_id}/sync",
            data=json.dumps({"expected_revision": revision}),
            content_type="application/json",
        )

    assert post(foreign.pk).status_code == 404
    assert post(repo.pk, 2).status_code == 409
    assert not Job.objects.exists()
    assert post(repo.pk).status_code == 200
    assert post(repo.pk).status_code == 409
    assert client.post(f"/api/environments/{environment.pk}/sync").status_code == 409


def test_check_worker_dispatch_failure_recovery_and_capacity(environment):
    target = str(environment.pk)
    job = Job.objects.create(kind="branch_check", target=target, status="RUNNING")
    with patch("core.branch_checks.check_environment") as check:
        perform_job(job)
    check.assert_called_once_with(environment.pk)
    job.refresh_from_db()
    assert job.status == "DONE"
    job.status, job.started_at = "RUNNING", timezone.now() - timedelta(minutes=6)
    job.save()
    recover_stale_jobs()
    job.refresh_from_db()
    environment.refresh_from_db()
    assert job.status == "ERROR"
    assert environment.status == "READY"
    Job.objects.create(kind="branch_check", target="991", status="RUNNING")
    Job.objects.create(kind="branch_check", target="992", status="RUNNING")
    queued = Job.objects.create(kind="branch_check", target=target)
    assert claim_job() is None
    queued.refresh_from_db()
    assert queued.status == "QUEUED"


@pytest.mark.django_db(transaction=True)
def test_repository_date_migration_preserves_references_without_inventing_a_date():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    old = [("core", "0052_single_active_ticket")]
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        stamp = timezone.now()
        environment = apps.get_model("core", "Environment").objects.create(name="Preserved dates", synced_at=stamp)
        observation = {"branch":"main", "local_sha":"a"*40, "status":"CURRENT", "checked_at":stamp.isoformat()}
        repo = apps.get_model("core", "EnvironmentRepository").objects.create(environment=environment,
            repository="team/preserved",branch="main",sha="a"*40,workspace="/retained/workspace",git_status=observation)
        analysis = apps.get_model("core", "Request").objects.create(environment=environment,
            need="Frozen investigation",baseline=[{"repository":repo.repository,"sha":repo.sha}])
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        migrated = current.get_model("core", "EnvironmentRepository").objects.get(pk=repo.pk)
        assert migrated.synced_at is None
        assert (migrated.sha, migrated.workspace, migrated.git_status) == (repo.sha, repo.workspace, observation)
        assert current.get_model("core", "Environment").objects.get(pk=environment.pk).synced_at == stamp
        assert current.get_model("core", "Request").objects.get(pk=analysis.pk).baseline == analysis.baseline
    finally:
        MigrationExecutor(connection).migrate(latest)
