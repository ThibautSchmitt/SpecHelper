"""Read bounded adapter model metadata without starting an inference session."""

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .auth import credential_directory, credential_lock, publish_refresh, subscription_credentials
from .vault import read as read_credential

IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,99}")


def read_claude_models(directory, env, timeout=12):
    """SDK initialize control request only; no user message or inference turn."""
    request = {"type": "control_request", "request_id": "spechelper-models",
               "request": {"subtype": "initialize", "hooks": {}}}
    response = subprocess.run(
        ["claude", "--print", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
         "--setting-sources", "", "--settings", '{"disableAllHooks":true}', "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}'],
        input=json.dumps(request)+"\n", cwd=directory, env=env, text=True, capture_output=True, timeout=timeout,
    )
    if len(response.stdout) > 1024*1024:
        raise ValueError("Model metadata exceeds bounds")
    for line in response.stdout.splitlines():
        value = json.loads(line)
        result = value.get("response", {}) if value.get("type") == "control_response" else {}
        if result.get("request_id") != "spechelper-models" or result.get("subtype") != "success":
            continue
        items = result.get("response", {}).get("models", [])
        if not isinstance(items, list) or len(items)>1000:
            raise ValueError("Invalid model catalog")
        models = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid model entry")
            identifier = item.get("value")
            if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
                continue
            efforts = item.get("supportedEffortLevels", []) if item.get("supportsEffort") is not False else []
            if not isinstance(efforts, list):
                efforts = []
            models.append({"identifier": identifier, "name": str(item.get("displayName") or identifier)[:100],
                           "capabilities": {"reasoning_efforts": [e for e in efforts if isinstance(e, str) and e in {"low", "medium", "high", "xhigh", "max"}], "default_effort": "", "is_default": item.get("isDefault") is True}})
        if not models:
            raise ValueError("No models were returned")
        return models
    raise ValueError("The CLI did not expose structured model metadata")


def read_codex_models(directory, env, timeout=10):
    """Only initialize/model-list RPCs are allowed; catalog presence is not entitlement."""
    process = subprocess.Popen(
        ["codex", "app-server", "--stdio"],
        cwd=directory,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    messages = queue.Queue(maxsize=128)

    def receive():
        try:
            for line in iter(lambda: process.stdout.readline(256001), ""):
                if len(line) > 256000 or not line.endswith("\n"):
                    break
                try:
                    messages.put_nowait(json.loads(line))
                except ValueError:
                    continue
                except queue.Full:
                    break
        finally:
            try:
                messages.put_nowait(None)
            except queue.Full:
                pass

    reader = threading.Thread(target=receive, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout

    def send(value):
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()

    def response(identifier):
        for _ in range(128):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Model discovery timed out")
            try:
                value = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("Model discovery timed out") from exc
            if value is None:
                raise ValueError("Model discovery stopped")
            if isinstance(value, dict) and value.get("id") == identifier:
                if "error" in value or not isinstance(value.get("result"), dict):
                    raise ValueError("Model discovery failed")
                return value["result"]
        raise ValueError("Too many model notifications")

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "spechelper", "version": "2.0"}},
            }
        )
        response(1)
        send({"method": "initialized", "params": {}})
        models, cursor, seen_cursors = [], None, set()
        for identifier in range(2, 12):
            send(
                {
                    "id": identifier,
                    "method": "model/list",
                    "params": {"limit": 100, "includeHidden": False, "cursor": cursor},
                }
            )
            page = response(identifier)
            items = page.get("data")
            if not isinstance(items, list) or len(items) > 100:
                raise ValueError("Invalid model catalog")
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Invalid model entry")
                model = item.get("model", item.get("id"))
                if not isinstance(model, str) or not IDENTIFIER.fullmatch(model):
                    raise ValueError("Invalid model identifier")
                if item.get("hidden") is True:
                    continue
                name = item.get("displayName")
                name = name if isinstance(name, str) and 0 < len(name) <= 100 else model
                efforts = item.get("supportedReasoningEfforts", [])
                if not isinstance(efforts, list):
                    efforts = []
                supported = [option.get("reasoningEffort") for option in efforts if isinstance(option, dict) and isinstance(option.get("reasoningEffort"), str) and option.get("reasoningEffort") in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}]
                models.append({"identifier": model, "name": name, "capabilities": {
                    "reasoning_efforts": list(dict.fromkeys(supported)),
                    "default_effort": item.get("defaultReasoningEffort") if item.get("defaultReasoningEffort") in supported else "",
                    "is_default": item.get("isDefault") is True,
                }})
            cursor = page.get("nextCursor")
            if cursor is None:
                return list({item["identifier"]: item for item in models}.values())
            if not isinstance(cursor, str) or len(cursor) > 2000 or cursor in seen_cursors:
                raise ValueError("Invalid model pagination")
            seen_cursors.add(cursor)
        raise ValueError("Model catalog exceeds bounds")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        process.stdin.close()
        reader.join(timeout=1)
        process.stdout.close()


def discover(root, provider, model=""):
    result = {
        "items": [],
        "state": "unavailable",
        "reason": "unsupported_cli",
        "checked_at": datetime.now(UTC).isoformat(),
        "access_verified": False,
    }
    directory = credential_directory(root, provider)
    if not subscription_credentials(directory, provider):
        return {**result, "reason": "not_connected"}
    if provider == "antigravity":
        from .antigravity import discover_models
        from .antigravity_auth import (
            OAUTH_MODE,
            credentials,
            inspect_cli,
            metadata_environment,
            oauth_profile_path,
            validate_oauth_profile,
        )
        from .vault import write as write_credential

        if inspect_cli()["state"] != "supported":
            return {**result, "state": "error", "reason": "refresh_failed"}
        try:
            # Hold the identity lock through refresh: rotating an OAuth refresh token
            # cannot race another metadata call or a new browser login.
            with credential_lock(root, provider):
                original = read_credential(directory / "auth.json")
                credential = credentials(directory)
                with tempfile.TemporaryDirectory(prefix="antigravity-models-") as temporary:
                    oauth = credential.get("credential") if credential["auth_mode"] == OAUTH_MODE else None
                    environment = metadata_environment(temporary, credential.get("api_key"), oauth)
                    value = discover_models(environment)
                    if model and any(entry["identifier"] == model for entry in value.get("items", [])):
                        from .antigravity import discover_effort

                        caps = discover_effort(environment, model)
                        for entry in value.get("items", []):
                            if entry["identifier"] == model:
                                entry["capabilities"] = caps
                    if oauth is not None:
                        rotated = validate_oauth_profile(json.loads(oauth_profile_path(temporary).read_text()))
                        if rotated != oauth and read_credential(directory / "auth.json") == original:
                            write_credential(directory / "auth.json", json.dumps({
                                "auth_mode": OAUTH_MODE, "credential": rotated,
                            }).encode())
            return {**result, **value}
        except (OSError, ValueError, subprocess.SubprocessError):
            return {**result, "state": "error", "reason": "refresh_failed"}
    if provider not in {"codex", "claude"}:
        return result
    try:
        with tempfile.TemporaryDirectory(prefix="spechelper-models-") as temporary:
            home = Path(temporary)
            if provider == "claude":
                target = home/".claude"
                target.mkdir(mode=0o700)
                with credential_lock(root, provider):
                    original = read_credential(directory/".credentials.json")
                (target/".credentials.json").write_bytes(original)
                (target/".credentials.json").chmod(0o600)
                env = {"PATH":os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME":temporary, "CLAUDE_CONFIG_DIR":str(target), "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC":"1"}
                items = read_claude_models(home, env)
                publish_refresh(root, provider, original, (target/".credentials.json").read_bytes())
                return {**result, "items": items, "state":"supported", "reason":"catalog_not_entitlement"}
            with credential_lock(root, provider):
                original = read_credential(directory / "auth.json")
            (home / "auth.json").write_bytes(original)
            (home / "auth.json").chmod(0o600)
            env = {
                "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "HOME": temporary,
                "CODEX_HOME": temporary,
            }
            items = read_codex_models(home, env)
            publish_refresh(root, provider, original, (home / "auth.json").read_bytes())
        return {**result, "items": items, "state": "supported", "reason": "catalog_not_entitlement"}
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError):
        return {**result, "state": "error", "reason": "refresh_failed"}
