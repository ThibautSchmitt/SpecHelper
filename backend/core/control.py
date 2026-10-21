"""Internal service credentials, generated automatically outside the agent workspace."""

import fcntl
import os
import secrets
from pathlib import Path


def private_value(path, create=False):
    path = Path(path)
    if not create:
        try:
            return path.read_text().strip()
        except OSError:
            return ""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        value = stream.read().strip()
        if not value:
            value = secrets.token_urlsafe(48)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    return value


def control_token(create=False, default_path="/control/runtime.token"):
    return os.environ.get("RUNTIME_TOKEN") or private_value(
        os.environ.get("CONTROL_TOKEN_FILE", default_path), create=create
    )
