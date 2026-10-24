"""Expose only authorized repository objects and this job's linked-worktree metadata."""

from pathlib import Path, PurePosixPath


def scoped_git_resources(data, workspace, repositories):
    cache = Path(data) / "git-cache"
    resources = {}
    for name in repositories:
        relative = PurePosixPath(name)
        if (
            not name
            or relative.is_absolute()
            or str(relative) != name
            or "\\" in name
            or any(part in {".", "..", ""} for part in name.split("/"))
        ):
            raise ValueError("Invalid authorized repository")
        repository = Path(workspace) / name
        if repository.resolve() != repository or not repository.is_dir():
            raise ValueError("Invalid authorized repository")
        gitfile = repository / ".git"
        if gitfile.is_dir() and not gitfile.is_symlink():
            # A self-contained synthetic repository needs no shared-cache mount.
            continue
        if gitfile.is_symlink() or not gitfile.is_file() or gitfile.stat().st_size > 8192:
            raise ValueError("Invalid linked-worktree metadata")
        value = gitfile.read_text().strip()
        if not value.startswith("gitdir: "):
            raise ValueError("Invalid linked-worktree metadata")
        metadata = Path(value[8:])
        if not metadata.is_absolute():
            metadata = repository / metadata
        metadata = metadata.absolute()
        if (
            metadata.resolve(strict=True) != metadata
            or not metadata.is_relative_to(cache)
            or metadata.parent.name != "worktrees"
        ):
            raise ValueError("Invalid linked-worktree metadata")
        common = metadata.parent.parent
        common_file = metadata / "commondir"
        if common_file.is_symlink() or common_file.stat().st_size > 8192:
            raise ValueError("Invalid linked-worktree metadata")
        if (metadata / common_file.read_text().strip()).resolve(strict=True) != common:
            raise ValueError("Invalid linked-worktree metadata")
        # The shared mirror may contain worktrees for other requests. Never expose
        # that directory, common reflogs, hooks or unrelated repository caches.
        for item in ("objects", "refs", "HEAD", "config", "packed-refs", "shallow"):
            source = common / item
            if source.exists():
                if source.resolve(strict=True) != source:
                    raise ValueError("Invalid repository metadata")
                resources[str(source)] = source
        resources[str(metadata)] = metadata
    return list(resources.values())


def mount_git_resources(data, resources):
    cache = Path(data) / "git-cache"
    command = ["--dir", str(cache)]
    parents = {cache}
    for source in resources:
        for parent in reversed(source.parent.parents):
            if parent.is_relative_to(cache) and parent not in parents:
                command += ["--dir", str(parent)]
                parents.add(parent)
        if source.parent not in parents:
            command += ["--dir", str(source.parent)]
            parents.add(source.parent)
        command += ["--ro-bind", str(source), str(source)]
    for parent in parents:
        command += ["--chmod", "0755", str(parent)]
    return command
