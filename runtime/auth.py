import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

from core.login import ACTIVE, PROVIDERS, TerminalLogin


@contextlib.contextmanager
def credential_lock(root, provider):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(root / ("." + provider + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def publish_refresh(root, provider, original, candidate):
    """Keep CLI token rotation across requests without replacing a newer login."""
    if candidate == original:
        return False
    try:
        old, new = json.loads(original), json.loads(candidate)
        key = "tokens" if provider == "codex" else "claudeAiOauth"
        mutable = (
            {"id_token", "access_token", "refresh_token"}
            if provider == "codex"
            else {"accessToken", "refreshToken", "expiresAt"}
        )
        if (
            old.keys() != new.keys()
            or not isinstance(old.get(key), dict)
            or not isinstance(new.get(key), dict)
        ):
            return False
        if old[key].keys() != new[key].keys():
            return False
        for name in old:
            if (
                name != key
                and not (provider == "codex" and name == "last_refresh")
                and old[name] != new[name]
            ):
                return False
        if any(old[key][name] != new[key][name] for name in old[key] if name not in mutable):
            return False
    except (ValueError, AttributeError, TypeError):
        return False
    name = "auth.json" if provider == "codex" else ".credentials.json"
    with credential_lock(root, provider):
        destination = credential_directory(root, provider) / name
        if not destination.exists() or destination.read_bytes() != original:
            return False
        temporary = destination.with_name(name + ".refresh")
        temporary.write_bytes(candidate)
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    return True


class Logins:
    def __init__(self, credential_root):
        self.credential_root = credential_root
        self.attempts = {}
        self.lock = threading.Lock()

    def start(self, attempt_id, provider):
        with self.lock:
            for login in self.attempts.values():
                if (
                    login.provider == provider
                    and login.public()["status"] in ACTIVE
                    and not login.cancelled.is_set()
                ):
                    raise ValueError("A connection is already in progress")

            def complete(home, env):
                source = home / provider
                files = (
                    ["auth.json"] if provider == "codex" else [".credentials.json", ".claude.json"]
                )
                required = files[0]
                if not (source / required).is_file():
                    raise ValueError("Authentication was not saved")
                destination = self.credential_root() / provider
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                with credential_lock(self.credential_root(), provider):
                    for name in files:
                        if (source / name).is_file():
                            temporary = destination / (name + ".new")
                            shutil.copyfile(source / name, temporary)
                            temporary.chmod(0o600)
                            os.replace(temporary, destination / name)
                return {"account": PROVIDERS[provider]}

            login = TerminalLogin(provider, complete)
            self.attempts[attempt_id] = login
            login.start()
            return login.public()

    def get(self, attempt_id):
        login = self.attempts.get(attempt_id)
        if not login:
            return {
                "status": "EXPIRED",
                "message": "The connection was interrupted. Try again.",
                "verification_uri": "",
                "user_code": "",
                "input_required": False,
            }
        return login.public()

    def submit(self, attempt_id, code):
        login = self.attempts.get(attempt_id)
        if not login:
            raise ValueError("The connection expired")
        login.submit(code)
        return login.public()

    def cancel(self, attempt_id):
        login = self.attempts.get(attempt_id)
        if login:
            login.cancel()
            if login.public()["status"] == "CONNECTED":
                return login.public()
        return {"status": "CANCELLED", "message": "Connection cancelled."}


def credential_directory(root: Path, provider):
    if (
        provider == "codex"
        and not (root / "codex" / "auth.json").exists()
        and (root / "auth.json").exists()
    ):
        return root  # Existing installations authenticated before browser buttons.
    return root / provider


def connection_status(root, provider):
    directory = credential_directory(root, provider)
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(directory),
        "CODEX_HOME": str(directory),
        "CLAUDE_CONFIG_DIR": str(directory),
        "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    command = (
        ["codex", "login", "status"]
        if provider == "codex"
        else ["claude", "auth", "status", "--json"]
    )
    result = subprocess.run(command, env=env, capture_output=True, timeout=10)
    return {
        "status": "CONNECTED" if result.returncode == 0 else "DISCONNECTED",
        "account": PROVIDERS[provider],
        "usage": "UNKNOWN",
        "reset": "UNKNOWN",
    }
