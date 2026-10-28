"""Bounded Antigravity metadata, headless protocol and permission observations.

This module never authenticates, imports a host session or launches inference itself.
The trusted supervisor owns credentials, isolation, cancellation and provider brokers.
"""

import json
import math
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime

PINNED_VERSION = "1.4.7"
MAX_METADATA = 1024 * 1024
MAX_STREAM = 64 * 1024 * 1024
MAX_EVENTS = 20000
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,99}$")
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
REQUIRED_FLAGS = {
    "--input-format", "--output-format", "--json-schema",
    "--model", "--disable-slash-commands", "--print-timeout",
}
USAGE_FIELDS = {
    "input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens", "total_tokens",
}
PERMISSION_LIMIT = "Antigravity could not use one or more tools under the granted permissions."


def cli_status(env, *, binary="agy", expected_version=PINNED_VERSION, timeout=10):
    """Inspect version/help only, with a caller-supplied isolated environment."""
    executable = shutil.which(binary, path=env.get("PATH", os.defpath))
    if not executable:
        return {"state": "unavailable", "reason": "missing_cli", "version": ""}
    try:
        results = [
            subprocess.run(
                [executable, option], env=env, capture_output=True,
                timeout=timeout, check=False,
            )
            for option in ("--version", "--help")
        ]
        if any(
            result.returncode or len(result.stdout) + len(result.stderr) > MAX_METADATA
            for result in results
        ):
            raise ValueError("CLI metadata unavailable")
        match = re.fullmatch(
            r"(?:Antigravity(?: CLI)?\s+)?v?(\d+)\.(\d+)\.(\d+)",
            results[0].stdout.decode(errors="replace").strip(),
        )
        if not match:
            return {"state": "unavailable", "reason": "incompatible_cli", "version": ""}
        version = ".".join(match.groups())
        numbers = tuple(map(int, match.groups()))
        help_text = (results[1].stdout + results[1].stderr).decode(errors="replace")
        flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", help_text))
        if (
            numbers[:2] != (1, 4) or numbers < (1, 4, 2)
            or (expected_version is not None and version != expected_version)
            or not REQUIRED_FLAGS <= flags
        ):
            return {"state": "unavailable", "reason": "incompatible_cli", "version": version}
        return {"state": "supported", "reason": "", "version": version}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"state": "error", "reason": "refresh_failed", "version": ""}


def model_family(identifier):
    """Recognize actual model brands, not the adapter or account display name."""
    value = identifier.lower()
    if value.startswith("gemini-"):
        return "google"
    if value.startswith("claude-"):
        return "anthropic"
    if value.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    return ""


def parse_models(stdout):
    """Parse the documented agy models table without inventing catalog rows."""
    if isinstance(stdout, bytes):
        if len(stdout) > MAX_METADATA:
            raise ValueError("Invalid model catalog")
        stdout = stdout.decode("utf-8")
    if not isinstance(stdout, str) or len(stdout.encode()) > MAX_METADATA:
        raise ValueError("Invalid model catalog")
    items, identifiers = [], set()
    for raw in ANSI.sub("", stdout).splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "...", "Available models", "Model", "SLUG", "Slug")):
            continue
        if line.lower().startswith(("error:", "warning:", "notice:", "note:", "usage:")):
            continue
        parts = re.split(r"\s+", line, maxsplit=1)
        if len(parts) != 2:
            continue
        identifier, name = parts
        if not IDENTIFIER.fullmatch(identifier) or not any(c in identifier for c in "-._/:"):
            continue
        if identifier in identifiers or len(items) >= 1000 or len(name) > 100:
            raise ValueError("Invalid model catalog")
        identifiers.add(identifier)
        item = {"identifier": identifier, "name": name.strip()}
        family = model_family(identifier)
        if family:
            item["family"] = family
        items.append(item)
    if not items:
        raise ValueError("Model discovery returned no usable identifiers")
    return items


def discover_models(env, *, binary="agy", timeout=10):
    """Read CLI catalog metadata; no prompt or provider turn is submitted."""
    executable = shutil.which(binary, path=env.get("PATH", os.defpath))
    if not executable:
        return {"state": "unavailable", "reason": "unsupported_cli", "items": []}
    try:
        result = subprocess.run(
            [executable, "models"], env=env, capture_output=True, timeout=timeout, check=False,
        )
        if result.returncode:
            failure = classify_failure(result.stderr)
            reason = "not_connected" if failure["kind"] == "AUTH_ERROR" else "refresh_failed"
            return {"state": "unavailable", "reason": reason, "items": [], "failure": failure}
        return {
            "state": "supported", "reason": "catalog_not_entitlement",
            "items": parse_models(result.stdout),
        }
    except subprocess.TimeoutExpired:
        return {"state": "error", "reason": "refresh_failed", "items": [], "failure": {"kind": "TIMEOUT"}}
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return {"state": "error", "reason": "refresh_failed", "items": []}


def discover_effort(env, model, timeout=8):
    """The documented headless /effort command must report zero inference turns."""
    if not IDENTIFIER.fullmatch(model):
        return {}
    try:
        result = subprocess.run(["agy", "-p", "/effort", "--output-format", "json", "--model", model], env=env, capture_output=True, timeout=timeout)
        if result.returncode or len(result.stdout)>MAX_METADATA:
            return {}
        response = json.loads(result.stdout)
        data = response.get("command", {}).get("data", {})
        if response.get("num_turns") != 0 or response.get("command", {}).get("name") != "effort":
            return {}
        efforts = data.get("available", []) if data.get("adjustable") else []
        if not isinstance(efforts, list):
            return {}
        return {"reasoning_efforts":[e for e in efforts if isinstance(e, str) and e in {"low", "medium", "high", "xhigh", "max"}], "default_effort":data.get("current", ""), "is_default":False}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def read_quota(env, *, timeout=10):
    """Read the pinned CLI's built-in usage report without submitting an agent turn."""
    result = subprocess.run(["agy", "-p", "/usage", "--output-format", "json"],
                            env=env, cwd=env["HOME"], capture_output=True, timeout=timeout)
    if result.returncode or len(result.stdout) > MAX_METADATA:
        raise ValueError("Quota metadata unavailable")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("status") != "SUCCESS" or type(value.get("num_turns")) is not int or value["num_turns"] != 0:
        raise ValueError("Invalid usage metadata")
    command, usage = value.get("command"), value.get("usage")
    if not isinstance(command, dict) or command.get("name") != "usage" or not isinstance(usage, dict):
        raise ValueError("Unsupported usage envelope")
    if any(usage.get(key) != 0 for key in USAGE_FIELDS):
        raise ValueError("Usage metadata must not consume inference")
    data = command.get("data")
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list) or len(groups) > 32:
        raise ValueError("Invalid quota groups")
    windows = {}
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("buckets"), list):
            raise ValueError("Invalid quota group")
        for bucket in group["buckets"]:
            if not isinstance(bucket, dict) or len(windows) >= 128:
                raise ValueError("Invalid quota bucket")
            identifier, fraction = bucket.get("id"), bucket.get("remaining_fraction")
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", identifier):
                raise ValueError("Invalid quota identifier")
            if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
                raise ValueError("Invalid quota fraction")
            pool = {"gemini-weekly": "gemini", "3p-weekly": "claude_gpt"}.get(identifier)
            window = {"remaining_percent": fraction * 100, "exhausted": fraction == 0,
                      "window_type": bucket.get("window", "other"), "source": "antigravity_cli",
                      "scope": "model_pool" if pool else "provider_limit", "limit_id": identifier,
                      "status": "observed"}
            if pool:
                window["model_pool"] = pool
            name = group.get("name")
            if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{0,95}", name):
                window["group_name"] = name
            reset = bucket.get("reset_time")
            if reset is not None:
                if not isinstance(reset, str):
                    raise ValueError("Invalid quota reset")
                parsed = datetime.fromisoformat(reset.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("Quota reset must include a timezone")
                window["resets_at"] = parsed.isoformat()
            if identifier in windows:
                raise ValueError("Duplicate quota identifier")
            windows[identifier] = window
    return windows


def headless_command(model, *, schema_path="/session/schema.json", timeout=300, binary="agy", effort=""):
    """Use one stdin turn, avoiding prompts in argv and implicit session resumption.

    Streamed input and -p are mutually exclusive in the native CLI. Fresh stdin
    streaming preserves the request and avoids --continue/--conversation entirely.
    """
    if not isinstance(model, str) or (model and not IDENTIFIER.fullmatch(model)):
        raise ValueError("Select an actual discovered Antigravity model")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ValueError("Invalid Antigravity invocation timeout")
    if schema_path != "/session/schema.json":
        raise ValueError("Invalid schema path")
    if effort not in {"", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("Unsupported Antigravity effort")
    return [
        binary, "--input-format", "stream-json", "--output-format", "stream-json",
        "--json-schema", schema_path, "--disable-slash-commands",
        "--print-timeout", f"{timeout}s",
    ] + (["--model", model] if model else []) + (["--effort", effort] if effort else [])


def prompt_message(prompt):
    """Encode one user turn; the supervisor closes stdin after this message."""
    if not isinstance(prompt, str) or len(prompt) > 200000:
        raise ValueError("Invalid Antigravity prompt")
    return (json.dumps({"event": "user", "message": {"content": prompt}}) + "\n").encode()


def classify_failure(detail):
    """Return fixed categories only; raw provider diagnostics never escape."""
    if isinstance(detail, bytes):
        detail = detail[-65536:].decode(errors="replace")
    text = str(detail)[-65536:].lower().replace("’", "'")
    if any(term in text for term in (
        "authentication required", "authentication_error", "invalid_grant",
        "unauthenticated", "unauthorized", "not logged in", "sign in required",
        "login required", "token expired", "invalid api key", "api_key_invalid",
        "gemini_api_key environment variable is not set", "gemini_api_key is not set",
    )):
        return {"kind": "AUTH_ERROR"}
    if any(term in text for term in (
        "invalid model", "model_not_found", "model not found", "unknown model",
        "unsupported model", "model is not available", "model does not exist",
    )):
        return {"kind": "MODEL_UNAVAILABLE"}
    if any(term in text for term in (
        "quota_exceeded", "quota exceeded", "insufficient_quota", "quota exhausted",
        "usage_limit_reached", "credits_required", "resource_exhausted",
    )):
        return {"kind": "QUOTA_EXHAUSTED"}
    if any(term in text for term in (
        "rate_limit", "rate limit", "too many requests", "overloaded",
    )):
        return {"kind": "BUSY"}
    if _permission_denied(text):
        return {"kind": "PERMISSION_DENIED"}
    if any(term in text for term in ("timed out", "timeout", "deadline exceeded")):
        return {"kind": "TIMEOUT"}
    return {"kind": "ERROR"}


def _permission_denied(text):
    return bool(re.search(
        r"(?:permission[_ -]?(?:denied|required)|soft[- ]den(?:y|ied)|"
        r"(?:tool|command)[^\n]{0,120}(?:denied|requires? approval|not allowed)|"
        r"(?:cannot|could not|unable to) obtain (?:approval|permission))", text, re.I,
    ))


def _usage(value):
    if not isinstance(value, dict):
        return {}
    return {
        key: item for key, item in value.items()
        if key in USAGE_FIELDS and isinstance(item, int) and not isinstance(item, bool)
        and 0 <= item <= 2**63 - 1
    }


def _conversation(value):
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except ValueError:
        return None


def parse_run(stdout, stderr=b"", returncode=0, *, timed_out=False, expected_model=""):
    """Require one valid terminal result, preserving safe tool-limit observations.

    Exit zero alone is insufficient. Soft permission refusals retain usable output
    as partial; without usable output they are explicit PERMISSION_DENIED failures.
    """
    if isinstance(stdout, bytes):
        if len(stdout) > MAX_STREAM:
            return {"failure": {"kind": "ERROR"}}
        stdout = stdout.decode(errors="replace")
    if not isinstance(stdout, str) or len(stdout.encode()) > MAX_STREAM:
        return {"failure": {"kind": "ERROR"}}
    if isinstance(stderr, bytes):
        stderr = stderr[-65536:].decode(errors="replace")
    stderr = str(stderr)[-65536:]
    denied = _permission_denied(stderr)
    errors, events, terminal = [], [], None
    conversation, selected_model = None, ""
    permissions = {}
    malformed, init_count = False, 0
    lines = stdout.splitlines()
    if len(lines) > MAX_EVENTS:
        return {"failure": {"kind": "ERROR"}}
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            malformed = True
            continue
        if not isinstance(event, dict):
            malformed = True
            continue
        kind = event.get("event")
        if not isinstance(kind, str) or kind not in {"init", "step_update", "result"}:
            malformed = True
            continue
        if terminal is not None:
            malformed = True
            continue
        detail = event.get(kind)
        if not isinstance(detail, dict):
            malformed = True
            continue
        candidate = event.get("conversation_id") if kind == "init" else detail.get("conversation_id")
        if candidate is not None:
            parsed = _conversation(candidate)
            if not parsed or (conversation is not None and parsed != conversation):
                malformed = True
            conversation = conversation or parsed
        if kind == "init":
            init_count += 1
            selected_model = detail.get("model", "")
            if not isinstance(selected_model, str) or (
                selected_model and not IDENTIFIER.fullmatch(selected_model)
            ):
                malformed = True
                selected_model = ""
            if detail.get("permission_mode") == "always-proceed":
                denied = True
                malformed = True
            mode = detail.get("permission_mode")
            if isinstance(mode, str) and re.fullmatch(r"[a-z-]{1,40}", mode):
                permissions["mode"] = mode
            tools = detail.get("tools")
            if isinstance(tools, list):
                permissions["tools"] = [
                    tool for tool in tools[:100]
                    if isinstance(tool, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", tool)
                ]
            events.append({"event": "init"})
        elif kind == "step_update":
            item = {"event": "step_update"}
            for key in ("state", "step_type", "tool_name"):
                value = detail.get(key)
                if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", value):
                    item[key] = value
            info = detail.get("tool_info")
            error = info.get("error") if isinstance(info, dict) else None
            if error:
                text = json.dumps(error, ensure_ascii=False)
                errors.append(text)
                refusal = _permission_denied(text)
                denied |= refusal
                item["tool_error"] = True
                if refusal:
                    item["permission_denied"] = True
            events.append(item)
        else:
            terminal = detail
            if detail.get("error"):
                errors.append(str(detail["error"]))
            denied |= _permission_denied(str(detail.get("error", "")))
            status = detail.get("status")
            if not isinstance(status, str) or status not in {
                "SUCCESS", "ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING",
            }:
                status = "INVALID"
                malformed = True
            events.append({"event": "result", "status": status})
    diagnostics = " ".join([*errors, stderr])
    usage = _usage(terminal.get("usage")) if terminal else {}
    result = {"usage": usage, "events": events[:1000], "permission_snapshot": permissions}
    if timed_out:
        return {**result, "timed_out": True, "failure": {"kind": "TIMEOUT"}}
    failure = classify_failure(diagnostics)
    if failure["kind"] not in {"ERROR", "PERMISSION_DENIED"}:
        return {**result, "failure": failure}
    if expected_model and selected_model and selected_model != expected_model:
        return {**result, "failure": {"kind": "MODEL_UNAVAILABLE"}}
    if (
        malformed or init_count != 1 or not terminal or not conversation
        or terminal.get("status") != "SUCCESS" or returncode
        or not isinstance(terminal.get("structured_output"), dict)
    ):
        if denied and failure["kind"] == "ERROR":
            failure = {"kind": "PERMISSION_DENIED"}
        return {**result, "failure": failure}
    result.update(
        output=terminal["structured_output"], session_id=conversation,
        model=selected_model or expected_model or "runtime-default",
    )
    if denied or errors:
        result.update(
            result_status="partial",
            permission_limits=[PERMISSION_LIMIT] if denied else [
                "Antigravity reported an unresolved tool error during this analysis."
            ],
        )
    return result
