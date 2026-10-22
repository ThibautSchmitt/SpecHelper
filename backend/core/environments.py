"""Administrative mutations; historical request workspaces are never changed here."""

import contextlib
import re
import shutil

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from . import github
from .git import environment_worktrees, lock, lock_key, remove_environment_worktree, run
from .git_sources import normalize_selection
from .models import DatabaseConnection, Environment, EnvironmentRepository, Job, Request


def validate(payload, environment_id=None):
    if Environment.objects.filter(name=payload.name).exclude(pk=environment_id).exists():
        raise HttpError(409, "This name already exists")
    for selection in payload.repositories:
        normalize_selection(selection)
    names = [r.repository.lower() for r in payload.repositories]
    if len(set(names)) != len(names):
        raise HttpError(422, "Duplicate project")
    for repo in payload.repositories:
        if not getattr(repo, "git_repository_id", None) and re.fullmatch(
            r"git-(github|gitlab)-[0-9a-f]{16}/[1-9][0-9]{0,31}(?:-[0-9a-f]{16})?", repo.repository
        ):
            raise HttpError(
                422,
                "Select the Git connection and remote repository instead of an internal source identifier.",
            )
        repo.repository = repo.repository.lower()
        github.validate_repository(repo.repository)
        run("check-ref-format", "refs/heads/" + repo.branch)
    if payload.database_id:
        get_object_or_404(DatabaseConnection, pk=payload.database_id)


@contextlib.contextmanager
def mutation_lock(environment_id):
    try:
        with lock(f"environment-{environment_id}", blocking=False):
            yield
    except BlockingIOError as exc:
        raise HttpError(
            409, "Synchronization is still using this environment. Try again afterwards."
        ) from exc


def writable(environment, expected_revision):
    if environment.revision != expected_revision:
        raise HttpError(409, "The environment has changed. Refresh the page before confirming.")
    if Job.objects.filter(kind="sync", target=str(environment.id), status="RUNNING").exists():
        raise HttpError(409, "Wait for the current synchronization to finish.")


@transaction.atomic
def update(environment_id, payload):
    with mutation_lock(environment_id):
        environment = get_object_or_404(Environment.objects.select_for_update(), pk=environment_id)
        writable(environment, payload.expected_revision)
        if Job.objects.filter(kind="sync", target=str(environment.id), status="QUEUED").exists():
            raise HttpError(409, "Synchronization is already scheduled.")
        validate(payload, environment_id)
        Request.objects.filter(environment=environment, environment_name_snapshot="").update(
            environment_name_snapshot=environment.name
        )
        existing = {r.repository: r for r in environment.repositories.all()}
        selected = {r.repository: r for r in payload.repositories}
        changed = []
        for name, repo in existing.items():
            if name not in selected:
                if repo.workspace:
                    environment.retired_worktrees.append(
                        {"repository": name, "workspace": repo.workspace}
                    )
                repo.delete()
        for name, selection in selected.items():
            repo = existing.get(name)
            if repo is None:
                EnvironmentRepository.objects.create(
                    environment=environment,
                    repository=name,
                    branch=selection.branch,
                    git_repository_id=getattr(selection, "git_repository_id", None),
                )
                changed.append(name)
            elif repo.branch != selection.branch or repo.git_repository_id != getattr(
                selection, "git_repository_id", None
            ):
                repo.branch = selection.branch
                repo.git_repository_id = getattr(selection, "git_repository_id", None)
                repo.sha = ""
                repo.save(update_fields=["branch", "sha", "git_repository"])
                changed.append(name)
        environment.name = payload.name
        environment.database_id = payload.database_id
        environment.revision += 1
        environment.status, environment.error = "PENDING", ""
        environment.save()
        Job.objects.create(
            kind="sync", target=str(environment.id), payload={"changed_repositories": changed}
        )
        return environment


@transaction.atomic
def delete(environment_id, confirmation):
    with mutation_lock(environment_id):
        environment = get_object_or_404(Environment.objects.select_for_update(), pk=environment_id)
        writable(environment, confirmation.expected_revision)
        if confirmation.confirm_name != environment.name:
            raise HttpError(409, "Explicitly confirm deletion of this environment.")
        repos = list(environment.repositories.all())
        worktrees = [
            {"repository": r.repository, "workspace": r.workspace} for r in repos
        ] + environment.retired_worktrees
        try:
            with contextlib.ExitStack() as stack:
                for name in sorted({lock_key(r["repository"]) for r in worktrees}):
                    stack.enter_context(lock(name, blocking=False))
                for name in sorted({r["repository"] for r in worktrees}):
                    for path in environment_worktrees(environment.id, name):
                        remove_environment_worktree(environment.id, name, path)
                for tree in worktrees:
                    remove_environment_worktree(
                        environment.id, tree["repository"], tree["workspace"]
                    )
                root = settings.DATA_DIR / "environments" / str(environment.id)
                if root.exists():
                    shutil.rmtree(root)
        except BlockingIOError as exc:
            raise HttpError(409, "A project is being prepared. Try again afterwards.") from exc
        Request.objects.filter(environment=environment, environment_name_snapshot="").update(
            environment_name_snapshot=environment.name
        )
        Job.objects.filter(kind="sync", target=str(environment.id)).delete()
        environment.delete()
