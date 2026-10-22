import contextlib
import fcntl
import hashlib
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import github
from .models import Environment, GitConnection, GitRepository


def run(*args, env=None, timeout=90):
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "gc.auto=0", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode:
        # Git stderr can contain transport details. Never persist it or expose it to agents.
        raise ValueError("Git failed: check the repository, branch and access rights")
    return result.stdout.strip()


@contextlib.contextmanager
def lock(name, blocking=True):
    # Branch selections and accounts may share one physical mirror. Serialize
    # every Git operation on that remote rather than on a branch-specific row.
    name = lock_key(name)
    root = settings.DATA_DIR / "locks"
    root.mkdir(parents=True, exist_ok=True)
    with (root / (hashlib.sha256(name.lower().encode()).hexdigest() + ".lock")).open("w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield


def lock_key(name):
    return (
        "mirror:" + str(mirror_path(name)) if name.startswith("git-") and source_for(name) else name
    )


def source_for(repository):
    if hasattr(repository, "git_repository_id"):
        return repository.git_repository if repository.git_repository_id else None
    if isinstance(repository, dict):
        return GitRepository.objects.filter(pk=repository.get("git_repository_id")).first()
    if isinstance(repository, str) and repository.startswith("git-"):
        from .git_sources import canonical

        return next(
            (
                source
                for source in GitRepository.objects.select_related("connection")
                if repository == canonical(source) or repository.startswith(canonical(source) + "-")
            ),
            None,
        )
    return None


def repository_name(repository):
    return (
        repository.get("repository")
        if isinstance(repository, dict)
        else getattr(repository, "repository", repository)
    )


def mirror_path(repository):
    source = source_for(repository)
    if source:
        identity = source.provider + "\0" + source.instance + "\0" + source.remote_id
        return (
            settings.DATA_DIR
            / "git-cache"
            / "remotes"
            / (hashlib.sha256(identity.encode()).hexdigest() + ".git")
        )
    repository = repository_name(repository)
    github.validate_repository(repository)
    owner, name = repository.lower().split("/")
    return settings.DATA_DIR / "git-cache" / owner / (name + ".git")


def fetch(repository):
    source = source_for(repository)
    mirror = mirror_path(repository)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    # Askpass is used only by the fetch process. Token is never placed in a remote URL or config.
    helper = Path(__file__).with_name("git_askpass.py")
    env = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(("GIT_", "SPECHELPER_"))
            and key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
        },
        "GIT_ASKPASS": str(helper),
        "GIT_TERMINAL_PROMPT": "0",
        "SPECHELPER_GIT_TOKEN": source_token(source),
        "SPECHELPER_GIT_USERNAME": "oauth2"
        if source and source.provider == "gitlab"
        else "x-access-token",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "http.followRedirects",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "credential.helper",
        "GIT_CONFIG_VALUE_1": "",
    }
    url = (
        source.clone_url if source else "https://github.com/" + repository_name(repository) + ".git"
    )
    try:
        if not mirror.exists():
            run("clone", "--mirror", "--", url, mirror, env=env, timeout=600)
        else:
            # Use the validated URL, independently of mutable origin configuration.
            run(
                "--git-dir",
                mirror,
                "fetch",
                "--prune",
                url,
                "+refs/heads/*:refs/heads/*",
                env=env,
                timeout=600,
            )
    except (ValueError, subprocess.TimeoutExpired):
        connection = (
            source.connection
            if source
            else GitConnection.objects.filter(legacy_source=True).first()
        )
        if connection:
            from .git_sources import fail_connection

            fail_connection(
                connection,
                "Git synchronization failed: check authentication and read permissions.",
            )
        raise
    return mirror


def source_token(source):
    if not source:
        legacy = GitConnection.objects.filter(legacy_source=True).first()
        if not legacy:
            return github.token()
        source = type("LegacySource", (), {"connection": legacy})()
    from .git_sources import Provider, fail_connection

    try:
        return Provider(source.connection).secret
    except ValueError as exc:
        fail_connection(source.connection, exc)
        raise


def materialize(mirror, destination, sha):
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        run("--git-dir", mirror, "worktree", "add", "--detach", destination, sha)
    if run("-C", destination, "rev-parse", "HEAD") != sha:
        raise ValueError("Git health check failed")
    return str(destination)


def remove_environment_worktree(environment_id, repository, workspace):
    if not workspace:
        return
    path = Path(workspace)
    root = settings.DATA_DIR / "environments" / str(environment_id)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Invalid workspace preparation path")
    if path.exists():
        run("--git-dir", mirror_path(repository), "worktree", "remove", path)


def environment_worktrees(environment_id, repository):
    root = (settings.DATA_DIR / "environments" / str(environment_id)).resolve()
    mirror = mirror_path(repository)
    if not root.exists() or not (mirror / "HEAD").exists():
        return []
    listing = run("--git-dir", mirror, "worktree", "list", "--porcelain")
    return [
        line[9:]
        for line in listing.splitlines()
        if line.startswith("worktree ")
        and Path(line[9:]).resolve().is_relative_to(root)
        and (
            not source_for(repository)
            or Path(line[9:]).parts[-len(Path(repository).parts) :] == Path(repository).parts
        )
    ]


def sync_environment(environment_id, changed_repositories=None):
    with lock(f"environment-{environment_id}"):
        environment = Environment.objects.get(pk=environment_id)
        Environment.objects.filter(pk=environment_id).update(status="SYNCING", error="")
        resolved = []
        try:
            for repo in environment.repositories.all().order_by("id"):
                with lock(repo.repository):
                    changed = (
                        changed_repositories is None
                        or repo.repository in changed_repositories
                        or not repo.sha
                    )
                    mirror = (
                        fetch(repo if repo.git_repository_id else repo.repository)
                        if changed
                        else mirror_path(repo)
                    )
                    sha = repo.sha
                    if changed:
                        if repo.sha:
                            run(
                                "--git-dir",
                                mirror,
                                "update-ref",
                                "refs/spechelper/retained/" + repo.sha,
                                repo.sha,
                            )
                        run("check-ref-format", "refs/heads/" + repo.branch)
                        sha = run(
                            "--git-dir",
                            mirror,
                            "rev-parse",
                            "--verify",
                            "refs/heads/" + repo.branch + "^{commit}",
                        )
                    run("--git-dir", mirror, "update-ref", "refs/spechelper/retained/" + sha, sha)
                    destination = (
                        settings.DATA_DIR
                        / "environments"
                        / str(environment_id)
                        / (sha if repo.git_repository_id else "")
                        / repo.repository
                    )
                    for old in environment_worktrees(environment_id, repo.repository):
                        if Path(old) != destination:
                            remove_environment_worktree(environment_id, repo.repository, old)
                    if repo.workspace and Path(repo.workspace) != destination:
                        remove_environment_worktree(environment_id, repo.repository, repo.workspace)
                    if destination.exists() and run("-C", destination, "rev-parse", "HEAD") != sha:
                        remove_environment_worktree(
                            environment_id, repo.repository, str(destination)
                        )
                    resolved.append((repo, sha, materialize(mirror, destination, sha)))
            if environment.database_id:
                from .postgres import check_connection

                check_connection(environment.database)
            active_workspaces = {workspace for _, _, workspace in resolved}
            for retired in environment.retired_worktrees:
                if retired["workspace"] in active_workspaces:
                    continue
                with lock(retired["repository"]):
                    remove_environment_worktree(
                        environment_id, retired["repository"], retired["workspace"]
                    )
            with transaction.atomic():
                for repo, sha, workspace in resolved:
                    repo.sha, repo.workspace = sha, workspace
                    repo.save(update_fields=["sha", "workspace"])
                Environment.objects.filter(pk=environment_id).update(
                    status="READY", error="", synced_at=timezone.now(), retired_worktrees=[]
                )
        except Exception as exc:
            Environment.objects.filter(pk=environment_id).update(
                status="ERROR",
                error=(
                    "Project download exceeded ten minutes. Retry synchronization."
                    if isinstance(exc, subprocess.TimeoutExpired)
                    else "Synchronization failed: check connections and branches."
                ),
            )
            raise


def request_workspace(request):
    root = settings.DATA_DIR / "analysis-workspaces" / str(request.id)
    root.mkdir(parents=True, exist_ok=True)
    for repo in request.baseline:
        with lock(repo["repository"]):
            destination = root / repo["repository"]
            materialize(mirror_path(repo), destination, repo["sha"])
    return root
