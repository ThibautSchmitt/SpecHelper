"""Release only UUID-owned role homes, never credentials or shared workspaces."""

import json
import shutil
from pathlib import Path
from uuid import UUID


def release(root, request_id, contexts):
    request_id = str(UUID(str(request_id)))
    wanted = {str(UUID(str(item))) for item in contexts}
    wanted.discard(request_id)  # legacy primary home is conversation-owned
    directory = Path(root) / "contexts" / request_id
    if any(path.is_symlink() for path in [directory, *directory.parents]):
        raise ValueError("Invalid session directory")
    if not directory.exists():
        directory.mkdir(parents=True, mode=0o700)
    # First create fences: a delayed request cannot recreate a retired home.
    for identifier in wanted:
        marker = directory / (".retired-" + identifier)
        if marker.is_symlink():
            raise ValueError("Invalid session marker")
        marker.touch(mode=0o600)
    for home in directory.iterdir():
        try:
            identifier = str(UUID(home.name))
        except ValueError:
            continue
        if home.is_symlink():
            raise ValueError("Invalid session directory")
        owner = home / ".spechelper-context"
        if owner.is_symlink():
            raise ValueError("Invalid session marker")
        context = ""
        if owner.is_file():
            try:
                context = json.loads(owner.read_text()[:100]).get("context", "")
            except (OSError, ValueError, AttributeError):
                pass
        if identifier in wanted or context in wanted:
            shutil.rmtree(home)
    return True
