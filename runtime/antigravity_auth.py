"""Explicit native Google OAuth and optional API credentials, outside analysis children."""

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .antigravity import PINNED_VERSION, cli_status
from .vault import read as read_credential

PROVIDER = "antigravity"
MODE = "gemini_api_key"
OAUTH_MODE = "google_oauth"
KEY = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
BROWSER_UNAVAILABLE = "Browser sign-in is not supported by this Antigravity runtime."
CLI_UNAVAILABLE = "Antigravity CLI is unavailable or incompatible."


def validate_oauth_profile(value):
    """Validate the pinned native consumer profile without assuming account eligibility."""
    if not isinstance(value, dict) or value.get("auth_method") != "consumer":
        raise ValueError("Invalid Antigravity OAuth profile.")
    token = value.get("token")
    if not isinstance(token, dict) or token.get("token_type") != "Bearer":
        raise ValueError("Invalid Antigravity OAuth profile.")
    for name in ("access_token", "refresh_token"):
        text = token.get(name)
        if not isinstance(text, str) or not 1 <= len(text) <= 16384 or any(ord(c) <= 32 or ord(c) == 127 for c in text):
            raise ValueError("Invalid Antigravity OAuth profile.")
    try:
        expiry = datetime.fromisoformat(token["expiry"].replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError("Invalid Antigravity OAuth profile.") from exc
    if len(json.dumps(value)) > 65536:
        raise ValueError("Invalid Antigravity OAuth profile.")
    return value


def oauth_profile_path(home):
    return Path(home) / ".gemini/antigravity-cli/antigravity-oauth-token"


def read_oauth_profile(home):
    """Read only a bounded regular native credential file, without following links."""
    path = oauth_profile_path(home)
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Invalid Antigravity profile location.")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
            raise ValueError("Invalid Antigravity OAuth profile.")
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("Invalid Antigravity OAuth profile.")
    return validate_oauth_profile(json.loads(data))


def write_oauth_profile(home, profile):
    """Materialize a profile only in an explicitly selected fresh native CLI home."""
    validate_oauth_profile(profile)
    path = oauth_profile_path(home)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Invalid Antigravity profile location.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(profile))
    path.chmod(0o600)
    return path


def synthetic_profile(home, access_token):
    """Child authentication is a broker capability, never the user's reusable token."""
    profile = {
        "auth_method": "consumer",
        "token": {"access_token": access_token, "refresh_token": "spechelper-synthetic-refresh",
                  "token_type": "Bearer", "expiry": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    }
    write_oauth_profile(home, profile)
    return profile


def credentials(directory):
    """Return an explicit encrypted identity credential, never environment keys."""
    value = json.loads(read_credential(Path(directory) / "auth.json"))
    if isinstance(value, dict) and set(value) == {"auth_mode", "credential"} and value["auth_mode"] == OAUTH_MODE:
        validate_oauth_profile(value["credential"])
        return value
    if (
        not isinstance(value, dict)
        or set(value) != {"auth_mode", "api_key"}
        or value["auth_mode"] != MODE
        or not isinstance(value["api_key"], str)
        or not KEY.fullmatch(value["api_key"])
    ):
        raise ValueError("Invalid Antigravity credential.")
    return value


def valid_credentials(directory):
    try:
        credentials(directory)
        return True
    except (OSError, ValueError, TypeError):
        return False


def metadata_environment(home, api_key=None, oauth_profile=None):
    """A clean trusted CLI home ignores host credentials, hooks and provider defaults."""
    home = Path(home)
    settings = home / ".gemini/antigravity-cli/settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if api_key is not None and oauth_profile is not None:
        raise ValueError("Choose one Antigravity authentication mode.")
    config = {"historySize": 0}
    if oauth_profile is None:
        config["modelProvider"] = "gemini"
    settings.write_text(json.dumps(config))
    settings.chmod(0o600)
    value = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "BROWSER": "/bin/false",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent",
    }
    if api_key is not None:
        value["GEMINI_API_KEY"] = api_key
    if oauth_profile is not None:
        write_oauth_profile(home, oauth_profile)
    return value


def inspect_cli():
    with tempfile.TemporaryDirectory(prefix="antigravity-metadata-") as temporary:
        return cli_status(metadata_environment(temporary), expected_version=PINNED_VERSION)


def status(directory, include_quota=False, *, root=None):
    """Configuration and CLI readiness are separate from successful provider access."""
    readiness = inspect_cli()
    value = {
        "status": "DISCONNECTED",
        "account": "Antigravity",
        "usage": "UNKNOWN",
        "reset": "UNKNOWN",
        "runtime_status": readiness,
        "authentication_mode": "api_key",
        "access_verified": False,
    }
    if readiness["state"] != "supported":
        value.update(status="ERROR", account=CLI_UNAVAILABLE)
    elif valid_credentials(directory):
        credential = credentials(directory)
        value.update(status="CONNECTED", account_key=account_key(directory),
                     authentication_mode="google_oauth" if credential["auth_mode"] == OAUTH_MODE else "api_key")
    if include_quota:
        value.update(quota_metadata(root or directory.parent, directory, value["status"] == "CONNECTED"))
    return value


def quota_metadata(root, directory, connected=True):
    """Read account usage in an isolated home under the normal credential lock."""
    from .antigravity import read_quota
    from .auth import credential_lock
    from .vault import write as write_credential

    metadata = {"state": "unavailable", "source": "antigravity_cli", "reason": "not_connected",
                "checked_at": datetime.now(UTC).isoformat()}
    if not connected:
        return {"quota_status": metadata}
    try:
        with credential_lock(root, PROVIDER):
            original = read_credential(directory / "auth.json")
            credential = credentials(directory)
            oauth = credential.get("credential") if credential["auth_mode"] == OAUTH_MODE else None
            with tempfile.TemporaryDirectory(prefix="antigravity-usage-") as temporary:
                environment = metadata_environment(temporary, credential.get("api_key"), oauth)
                try:
                    windows = read_quota(environment)
                finally:
                    if oauth is not None:
                        rotated = validate_oauth_profile(json.loads(oauth_profile_path(temporary).read_text()))
                        if rotated != oauth and read_credential(directory / "auth.json") == original:
                            write_credential(directory / "auth.json", json.dumps({"auth_mode": OAUTH_MODE, "credential": rotated}).encode())
        metadata.update(state="available" if windows else "unavailable", reason="" if windows else "not_reported")
        return {"quota_status": metadata, "quota_windows": windows}
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return {"quota_status": {**metadata, "state": "error", "reason": "refresh_failed"}}


def account_key(directory):
    """Equal explicitly entered API credentials share capacity; no account guessing."""
    try:
        value = credentials(directory)
        if value["auth_mode"] == OAUTH_MODE:
            # Native profiles do not guarantee a stable account subject. Token
            # rotation is not evidence of a new account, so do not fingerprint it.
            return ""
        key = value["api_key"]
        return hashlib.sha256(("antigravity:" + value["auth_mode"] + ":" + key).encode()).hexdigest()
    except (OSError, ValueError, TypeError):
        return ""


def prepare_session(session, token=None, auth_mode=MODE):
    """Expose only explicit scoped read tools; filesystem/network enforcement is external."""
    settings = Path(session) / ".gemini/antigravity-cli/settings.json"
    if any(path.is_symlink() for path in (settings, *settings.parents)):
        raise ValueError("Invalid Antigravity session.")
    settings.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    commands = ("git", "rg", "ls", "cat", "sed", "head", "tail", "find", "readlink", "wc", "python3", "curl")
    config = {
        "historySize": 0,
        "trustedWorkspaces": ["/workspace"],
        "permissions": {
            "allow": ["command(" + command + ")" for command in commands]
            + ["read_file(" + path + ")" for path in ("/workspace", "/skills", "/context", "/attachments")]
            # The CLI may inspect its service-authored output schema before
            # finishing. Grant this exact file, never the session directory.
            + ["read_file(/session/schema.json)"],
            "deny": ["write_file(*)"],
        },
    }
    if auth_mode == OAUTH_MODE:
        if token is None:
            raise ValueError("Antigravity OAuth broker capability required.")
        synthetic_profile(session, token)
    elif auth_mode == MODE:
        config["modelProvider"] = "gemini"
    else:
        raise ValueError("Invalid Antigravity authentication mode.")
    settings.write_text(json.dumps(config))
    settings.chmod(0o600)
    return config["permissions"]
