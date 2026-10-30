#!/usr/local/bin/python
"""Resolve immutable base CLIs or atomically activated, read-only tool releases."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

COMMANDS = {"codex": "codex", "claude": "claude", "antigravity": "agy"}
TOOLS = Path(os.environ.get("CLI_TOOLS_ROOT", "/cli-tools"))
BASE_VERSIONS = Path("/usr/local/share/spechelper-cli-versions.json")
VERSION = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,4}")


def version_key(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("Invalid stable CLI version")
    return tuple(int(part) for part in value.split("."))


def base_versions():
    try:
        return json.loads(BASE_VERSIONS.read_text())
    except (OSError, ValueError):
        return {}


def tool_path(provider):
    command = COMMANDS[provider]
    original = Path("/usr/local/bin") / (command + "-base")
    if not original.exists():
        original = Path("/usr/local/bin") / command
    try:
        active = (TOOLS / provider / "current").resolve(strict=True)
        relative = active.relative_to(TOOLS / provider / "releases")
        if len(relative.parts) != 1:
            raise ValueError("Invalid active release")
        installed = version_key(relative.name)
        pinned = base_versions().get(provider, "")
        if pinned and version_key(pinned) >= installed:
            return original
        executable = active / "bin" / command
        resolved = executable.resolve(strict=True)
        resolved.relative_to(active)
        if executable.is_file() and os.access(executable, os.X_OK):
            return executable
    except (OSError, ValueError):
        pass
    return original


def read_version(executable):
    result = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True,
        timeout=8, check=True,
        env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp", "DISABLE_AUTOUPDATER": "1"},
    )
    match = re.search(r"(?<![\d.])(\d{1,4}\.\d{1,4}\.\d{1,4})(?![\d.])", result.stdout[:4096])
    if not match:
        raise ValueError("CLI did not report a version")
    return match.group(1)


def installed_versions():
    values = {}
    for provider in COMMANDS:
        try:
            values[provider] = read_version(tool_path(provider))
        except (OSError, ValueError, subprocess.SubprocessError):
            values[provider] = ""
    return values


if __name__ == "__main__":
    alias = Path(sys.argv[0]).name
    provider = next((key for key, command in COMMANDS.items() if command == alias), None)
    if provider:
        executable = str(tool_path(provider))
        os.execv(executable, [executable, *sys.argv[1:]])
    elif sys.argv[1:] == ["--snapshot-base"]:
        BASE_VERSIONS.write_text(json.dumps(installed_versions()))
    else:
        print(json.dumps(installed_versions()))
