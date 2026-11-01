"""Observe remote heads without moving an environment or an analysis baseline."""

import subprocess
import time
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import git
from .models import Environment, EnvironmentRepository, Job

CHECK_INTERVAL = timedelta(minutes=5)
ACTIVE = ["QUEUED", "RUNNING"]


def observation(repo, status, **details):
    return {
        "branch": repo.branch,
        "local_sha": repo.sha,
        "status": status,
        "checked_at": timezone.now().isoformat(),
        **details,
    }


def describe(repo):
    value = repo.git_status
    checked = parse_datetime(value.get("checked_at", "")) if value else None
    if (
        not checked
        or timezone.is_naive(checked)
        or checked < timezone.now() - CHECK_INTERVAL * 3
        or value.get("local_sha") != repo.sha
        or value.get("branch") != repo.branch
    ):
        return {"status": "UNKNOWN"}
    return value


def summary(repositories):
    states = [describe(repo)["status"] for repo in repositories]
    if not states or any(state in {"UNKNOWN", "UNAVAILABLE", "MISSING"} for state in states):
        return "UNKNOWN"
    current = states.count("CURRENT")
    return "SYNCED" if current == len(states) else "PARTIAL" if current else "OUTDATED"


def schedule_due():
    """One reusable queue entry per environment, coordinated by its row lock."""
    now = timezone.now()
    ids = list(
        Environment.objects.filter(next_git_check_at__lte=now)
        .exclude(status__in=["PENDING", "SYNCING"])
        .values_list("pk", flat=True)[:100]
    )
    for environment_id in ids:
        with transaction.atomic():
            environment = Environment.objects.select_for_update().filter(pk=environment_id).first()
            if not environment or environment.next_git_check_at > now:
                continue
            if (
                environment.status in {"PENDING", "SYNCING"}
                or Job.objects.filter(
                    kind__in=["sync", "branch_check"],
                    target=str(environment_id),
                    status__in=ACTIVE,
                ).exists()
            ):
                continue
            job = Job.objects.filter(kind="branch_check", target=str(environment_id)).first()
            if job:
                job.status, job.error, job.payload = "QUEUED", "", {}
                job.started_at = job.finished_at = None
                job.created_at = now
                job.save()
            else:
                Job.objects.create(kind="branch_check", target=str(environment_id))
            environment.next_git_check_at = now + CHECK_INTERVAL
            environment.save(update_fields=["next_git_check_at"])


def check_environment(environment_id):
    deadline = time.monotonic() + 240
    with git.lock(f"environment-{environment_id}"):
        environment = Environment.objects.filter(pk=environment_id).first()
        if (
            not environment
            or Job.objects.filter(
                kind="sync",
                target=str(environment_id),
                status__in=ACTIVE,
            ).exists()
        ):
            return
        fetched = set()
        for repo in environment.repositories.select_related("git_repository__connection").order_by(
            "id"
        ):
            try:
                remaining = int(deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError
                with git.lock(repo.repository):
                    mirror = git.mirror_path(repo)
                    # Preserve a force-pushed-away baseline before fetching/pruning refs.
                    if repo.sha and mirror.exists():
                        git.run(
                            "--git-dir",
                            mirror,
                            "update-ref",
                            "refs/spechelper/retained/" + repo.sha,
                            repo.sha,
                        )
                    if mirror not in fetched:
                        mirror = git.fetch(
                            repo if repo.git_repository_id else repo.repository,
                            timeout=min(60, remaining),
                        )
                        fetched.add(mirror)
                    git.run("check-ref-format", "refs/heads/" + repo.branch)
                    try:
                        remote = git.run(
                            "--git-dir",
                            mirror,
                            "rev-parse",
                            "--verify",
                            "refs/heads/" + repo.branch + "^{commit}",
                        )
                    except ValueError:
                        value = observation(repo, "MISSING")
                    else:
                        if not repo.sha:
                            value = observation(repo, "UNINITIALIZED", remote_sha=remote)
                        else:
                            ahead, behind = map(
                                int,
                                git.run(
                                    "--git-dir",
                                    mirror,
                                    "rev-list",
                                    "--left-right",
                                    "--count",
                                    repo.sha + "..." + remote,
                                ).split(),
                            )
                            state = (
                                "DIVERGED"
                                if ahead and behind
                                else "BEHIND"
                                if behind
                                else "AHEAD"
                                if ahead
                                else "CURRENT"
                            )
                            value = observation(
                                repo, state, remote_sha=remote, ahead=ahead, behind=behind
                            )
            except (ValueError, subprocess.TimeoutExpired, TimeoutError, OSError):
                value = observation(repo, "UNAVAILABLE")
            EnvironmentRepository.objects.filter(
                pk=repo.pk, branch=repo.branch, sha=repo.sha
            ).update(git_status=value)
