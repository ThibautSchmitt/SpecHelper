"""Install only named official CLI releases, without application credentials or Docker access."""

import json
import os
import platform
import secrets
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from .cli_tools import COMMANDS, TOOLS, installed_versions, read_version, version_key

PACKAGES = {"codex": "@openai/codex", "claude": "@anthropic-ai/claude-code"}
AGY_RELEASES = "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/"
TOKEN_FILE = Path(os.environ.get("CLI_MAINTENANCE_TOKEN_FILE", "/cli-control/token"))
CACHE_SECONDS = 24 * 3600
LOCK = threading.Lock()
OPERATIONS = {}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def operation_state(key):
    if key not in OPERATIONS:
        try:
            OPERATIONS[key] = json.loads((TOOLS / ".operations" / (key + ".json")).read_text())
        except (OSError, ValueError):
            return {"status": "UNKNOWN"}
    return OPERATIONS[key]


def save_operation(key, value):
    directory = TOOLS / ".operations"
    directory.mkdir(exist_ok=True)
    temporary = directory / (key + ".tmp")
    temporary.write_text(json.dumps(value))
    os.replace(temporary, directory / (key + ".json"))
    OPERATIONS[key] = value


def authorize(authorization: str = Header(default="")):
    try:
        expected = TOKEN_FILE.read_text().strip()
    except OSError:
        expected = ""
    if not expected or not secrets.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(401, "Access denied")


def public_json(url):
    # Fixed release registries only. Never send ambient credentials or follow redirects.
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError("Release metadata exceeds its bound")
    return json.loads(data)


def release(provider, version=None):
    if provider in PACKAGES:
        requested = version or "latest"
        if version:
            version_key(version)
        data = public_json(f"https://registry.npmjs.org/{PACKAGES[provider]}/{requested}")
        candidate = data.get("version", "")
        version_key(candidate)
        if data.get("name") != PACKAGES[provider] or (version and candidate != version):
            raise ValueError("Unexpected official package")
        return {"version": candidate}
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if provider != "antigravity" or not architecture:
        raise ValueError("Unsupported CLI platform")
    data = public_json(AGY_RELEASES + "linux_" + architecture + ".json")
    version_key(data.get("version", ""))
    if version and data["version"] != version:
        raise ValueError("The official Antigravity release changed; check again")
    return {"version": data["version"], "platforms": {architecture: data}}


def inventory(force=False):
    cache_path = TOOLS / "release-cache.json"
    try:
        cached = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cached = {}
    retry_seconds = 300 if any(row.get("state") == "unavailable" for row in cached.get("items", {}).values()) else CACHE_SECONDS
    if force or time.time() - cached.get("checked", 0) >= retry_seconds:
        rows = {}
        for provider in COMMANDS:
            try:
                rows[provider] = {"latest_version": release(provider)["version"], "state": "available"}
            except (OSError, ValueError, httpx.HTTPError):
                rows[provider] = {**cached.get("items", {}).get(provider, {}), "state": "unavailable"}
        cached = {"checked": time.time(), "items": rows}
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(cached))
        os.replace(temporary, cache_path)
    installed = installed_versions()
    return {"items": [{"agent": provider, "installed_version": installed[provider], **cached.get("items", {}).get(provider, {})} for provider in COMMANDS]}


class Installation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: Literal["codex", "claude", "antigravity"]
    version: str
    operation_id: uuid.UUID


def install(payload):
    version_key(payload.version)
    provider, command = payload.agent, COMMANDS[payload.agent]
    active = TOOLS / provider / "current"
    previous = os.readlink(active) if active.is_symlink() else ""
    destination = TOOLS / provider / "releases" / payload.version
    if active.is_symlink() and active.resolve() == destination:
        return {"agent": provider, "installed_version": read_version(destination / "bin" / command), "previous": previous}
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("Invalid CLI release directory")
    official = release(provider, payload.version)
    if provider in PACKAGES:
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "NPM_CONFIG_CACHE": str(TOOLS / ".npm-cache"), "DISABLE_AUTOUPDATER": "1"}
        subprocess.run(
            ["npm", "install", "--prefix", str(destination), "--omit=dev", "--no-audit", "--no-fund", "--userconfig=/dev/null", "--globalconfig=/etc/spechelper-npmrc", "--registry=https://registry.npmjs.org", PACKAGES[provider] + "@" + payload.version],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900, check=True,
        )
        (destination / "bin").mkdir(exist_ok=True)
        executable = destination / "bin" / command
        if not executable.exists():
            executable.symlink_to(Path("../node_modules/.bin") / command)
    else:
        from scripts.install_antigravity import install as install_agy

        (destination / "bin").mkdir(exist_ok=True)
        manifest = destination / "release.json"
        manifest.write_text(json.dumps(official))
        install_agy(manifest, destination / "bin" / command)
    executable = destination / "bin" / command
    executable.resolve(strict=True).relative_to(destination)
    if read_version(executable) != payload.version:
        raise ValueError("Installed CLI version does not match its release")
    return {"agent": provider, "installed_version": payload.version, "previous": previous}


@app.get("/health", dependencies=[Depends(authorize)])
def health():
    return {"status": "ok"}


@app.get("/inventory", dependencies=[Depends(authorize)])
def read_inventory():
    with LOCK:
        return inventory()


@app.get("/release/antigravity", dependencies=[Depends(authorize)])
def current_antigravity_release():
    # The rolling official manifest cannot resolve an older cached version.
    try:
        candidate = release("antigravity")
    except (OSError, ValueError, httpx.HTTPError):
        raise HTTPException(502, "Official CLI release information is unavailable.") from None
    return {"agent": "antigravity", "latest_version": candidate["version"]}


@app.get("/operations/{operation_id}", dependencies=[Depends(authorize)])
def operation(operation_id: uuid.UUID):
    return operation_state(str(operation_id))


@app.post("/install", dependencies=[Depends(authorize)])
def install_release(payload: Installation):
    try:
        version_key(payload.version)
    except ValueError as error:
        raise HTTPException(422, "Invalid stable CLI version") from error
    key = str(payload.operation_id)
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, "CLI maintenance is already running")
    try:
        if operation_state(key).get("status") in {"STAGED", "ACTIVE", "DONE"}:
            return operation_state(key)
        OPERATIONS[key] = {"status": "RUNNING"}
        result = install(payload)
        save_operation(key, {"status": "STAGED", **result})
        return OPERATIONS[key]
    except (OSError, ValueError, subprocess.SubprocessError, httpx.HTTPError):
        OPERATIONS[key] = {"status": "ERROR"}
        raise HTTPException(502, "CLI installation failed. The previous executable is preserved.") from None
    finally:
        LOCK.release()


@app.post("/activate/{operation_id}", dependencies=[Depends(authorize)])
def activate_release(operation_id: uuid.UUID):
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, "CLI maintenance is already running")
    try:
        operation = operation_state(str(operation_id))
        if operation["status"] not in {"STAGED", "ACTIVE", "DONE"}:
            raise HTTPException(409, "No staged CLI release")
        if operation["status"] in {"ACTIVE", "DONE"}:
            return operation
        provider, version = operation["agent"], operation["installed_version"]
        active = TOOLS / provider / "current"
        destination = TOOLS / provider / "releases" / version
        temporary = active.with_name("current-" + str(operation_id))
        temporary.symlink_to(destination)
        save_operation(str(operation_id), {**operation, "status": "ACTIVE", "activated_at": time.time()})
        os.replace(temporary, active)
        return operation_state(str(operation_id))
    finally:
        LOCK.release()


@app.post("/rollback/{operation_id}", dependencies=[Depends(authorize)])
def rollback_release(operation_id: uuid.UUID):
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, "CLI maintenance is already running")
    try:
        operation = operation_state(str(operation_id))
        if operation["status"] not in {"STAGED", "ACTIVE", "DONE", "ROLLED_BACK"}:
            raise HTTPException(409, "Unknown CLI operation")
        provider = operation["agent"]
        active = TOOLS / provider / "current"
        if operation["status"] in {"STAGED", "ROLLED_BACK"}:
            save_operation(str(operation_id), {**operation, "status": "ROLLED_BACK"})
            return {"status": "ROLLED_BACK", "installed_version": installed_versions()[provider]}
        expected = TOOLS / provider / "releases" / operation["installed_version"]
        if not active.is_symlink() or active.resolve() != expected:
            # The journal is written before activation. A crash may leave the
            # previous target intact; recognize this without reverting a newer one.
            previous_unchanged = (active.is_symlink() and str(active.resolve()) == operation["previous"]) if operation["previous"] else not active.is_symlink()
            if previous_unchanged:
                save_operation(str(operation_id), {**operation, "status": "ROLLED_BACK"})
                return {"status": "ROLLED_BACK", "installed_version": installed_versions()[provider]}
            raise HTTPException(409, "A newer CLI operation has already changed this release")
        if operation["previous"]:
            previous = Path(operation["previous"])
            relative = previous.relative_to(TOOLS / provider / "releases")
            if len(relative.parts) != 1:
                raise HTTPException(409, "Invalid previous release")
            version_key(relative.name)
            temporary = active.with_name("rollback-" + str(operation_id))
            temporary.symlink_to(previous)
            os.replace(temporary, active)
        elif active.is_symlink():
            active.unlink()
        save_operation(str(operation_id), {**operation, "status": "ROLLED_BACK"})
        return {"status": "ROLLED_BACK", "installed_version": installed_versions()[provider]}
    finally:
        LOCK.release()


@app.post("/confirm/{operation_id}", dependencies=[Depends(authorize)])
def confirm_release(operation_id: uuid.UUID):
    with LOCK:
        operation = operation_state(str(operation_id))
        if operation["status"] not in {"ACTIVE", "DONE"}:
            raise HTTPException(409, "No activated CLI release")
        save_operation(str(operation_id), {**operation, "status": "DONE"})
        return {"status": "DONE"}
