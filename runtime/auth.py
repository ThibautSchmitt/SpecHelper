import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from core.login import ACTIVE, PROVIDERS, TerminalLogin

from .quota import app_server_windows, read_codex_quota


def identity_root(root, identity_id=None):
    """Legacy credentials stay put; additional identities have isolated namespaces."""
    return root / "identities" / str(uuid.UUID(str(identity_id))) if identity_id else root


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

    def start(self, attempt_id, provider, identity_id=None):
        target_root = identity_root(self.credential_root(), identity_id)
        with self.lock:
            for login in self.attempts.values():
                if (
                    login.provider == provider
                    and getattr(login, "identity_id", None) == identity_id
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
                destination = target_root / provider
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                with credential_lock(target_root, provider):
                    for name in files:
                        if (source / name).is_file():
                            temporary = destination / (name + ".new")
                            shutil.copyfile(source / name, temporary)
                            temporary.chmod(0o600)
                            os.replace(temporary, destination / name)
                return {
                    "account": PROVIDERS[provider],
                    "account_key": account_key(destination, provider),
                }

            login = TerminalLogin(provider, complete)
            login.identity_id = identity_id
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


def connection_status(root, provider, include_quota=False):
    directory = credential_directory(root, provider)
    if not subscription_credentials(directory, provider):
        value = {
            "status": "DISCONNECTED",
            "account": PROVIDERS[provider],
            "usage": "UNKNOWN",
            "reset": "UNKNOWN",
        }
        if include_quota:
            value.update(quota_status(root, directory, provider, "DISCONNECTED"))
        return value
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
    value = {
        "status": "CONNECTED" if result.returncode == 0 else "DISCONNECTED",
        "account": PROVIDERS[provider],
        "usage": "UNKNOWN",
        "reset": "UNKNOWN",
        "account_key": account_key(directory, provider),
    }
    if include_quota:
        value.update(quota_status(root, directory, provider, value["status"]))
    return value


def quota_status(root, directory, provider, status):
    """Only supported non-inference account reads; never scrape private OAuth APIs."""
    metadata = {
        "state": "unavailable",
        "source": "codex_app_server" if provider == "codex" else "claude_cli",
        "checked_at": datetime.now(UTC).isoformat(),
        "reason": "not_connected" if status != "CONNECTED" else "unsupported_cli",
    }
    if status != "CONNECTED" or provider != "codex":
        return {"quota_status": metadata}
    try:
        # A clean home prevents project configuration, plugins and MCP startup.
        with tempfile.TemporaryDirectory(prefix="spechelper-usage-") as temporary:
            home = Path(temporary)
            with credential_lock(root, provider):
                original = (directory / "auth.json").read_bytes()
            (home / "auth.json").write_bytes(original)
            (home / "auth.json").chmod(0o600)
            env = {
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "HOME": temporary,
                "CODEX_HOME": temporary,
            }
            snapshot = read_codex_quota(home, env)
            account = json.loads(original).get("tokens", {}).get("account_id")
            if snapshot.get("accountId") and snapshot["accountId"] != account:
                raise ValueError("Quota identity mismatch")
            windows = app_server_windows(snapshot)
            # A successful read may rotate OAuth credentials; preserve only safe rotation.
            publish_refresh(root, provider, original, (home / "auth.json").read_bytes())
            metadata.update(
                state="available" if windows else "unavailable",
                reason="" if windows else "not_reported",
            )
            return {
                "quota_status": metadata,
                "quota_windows": windows,
                "ordinary_usage_allowed": snapshot.get("ordinaryUsageAllowed") is True,
            }
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError):
        metadata.update(state="error", reason="refresh_failed")
        return {"quota_status": metadata}


def account_key(directory, provider):
    """Opaque quota grouping from provider account IDs, never a display-name guess."""
    try:
        filename = "auth.json" if provider == "codex" else ".claude.json"
        value = json.loads((directory / filename).read_text())
        identifier = (
            value.get("tokens", {}).get("account_id")
            if provider == "codex"
            else value.get("oauthAccount", {}).get("accountUuid")
        )
        if isinstance(identifier, str) and identifier:
            return hashlib.sha256((provider + ":" + identifier).encode()).hexdigest()
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ""


def subscription_credentials(directory, provider):
    """Subscription OAuth only: an administrator's billed API key is never inherited."""
    try:
        filename = "auth.json" if provider == "codex" else ".credentials.json"
        value = json.loads((directory / filename).read_text())
        if provider == "codex":
            return bool(
                isinstance(value.get("tokens"), dict)
                and value["tokens"].get("access_token")
                and not value.get("OPENAI_API_KEY")
                and value.get("auth_mode") not in {"apikey", "api_key"}
            )
        if any(value.get(key) for key in ("ANTHROPIC_API_KEY", "apiKey", "anthropicApiKey")):
            return False
        return bool(
            isinstance(value.get("claudeAiOauth"), dict)
            and value["claudeAiOauth"].get("accessToken")
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def claude_metadata(data):
    """Keep OAuth identity metadata, excluding paid keys, helpers and executable config."""
    try:
        source = json.loads(data)
    except (ValueError, TypeError):
        return {}
    if not isinstance(source, dict):
        return {}
    result = {}
    account = source.get("oauthAccount")
    if isinstance(account, dict):
        result["oauthAccount"] = {
            key: value
            for key, value in account.items()
            if key
            in {
                "accountUuid",
                "organizationUuid",
                "emailAddress",
                "organizationName",
                "displayName",
            }
            and isinstance(value, str)
        }
    if isinstance(source.get("hasCompletedOnboarding"), bool):
        result["hasCompletedOnboarding"] = source["hasCompletedOnboarding"]
    if isinstance(source.get("lastOnboardingVersion"), str):
        result["lastOnboardingVersion"] = source["lastOnboardingVersion"]
    return result
