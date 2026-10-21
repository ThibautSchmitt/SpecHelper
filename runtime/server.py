"""Internal runtime. Its API is never published by Compose."""

import json
import os
import secrets
import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.control import control_token
from core.postgres import query

from .auth import Logins, connection_status, credential_directory, publish_refresh

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
DATA = Path(os.environ.get("SPECHELPER_DATA_DIR", "/data"))
SESSIONS = Path(os.environ.get("SESSION_DIR", "/sessions"))
CREDENTIALS = Path(os.environ.get("AI_CREDENTIALS_DIR", "/credentials"))
capabilities: dict[str, dict] = {}
locks: dict[str, threading.Lock] = {}
guard = threading.Lock()
logins = Logins(lambda: CREDENTIALS)


def authorize(authorization: str = Header(default="")):
    expected = control_token()
    if not expected or not secrets.compare_digest(authorization, "Bearer " + expected):
        raise HTTPException(401, "Unauthorized runtime")


class RunIn(BaseModel):
    request_id: uuid.UUID
    context_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    agent: Literal["codex", "claude"] = "codex"
    phase: Literal["understanding", "analysis"] = "analysis"
    profile: Literal[
        "requirement",
        "code",
        "attachment",
        "reviewer_writer",
        "code_writer",
        "writer",
        "independent",
        "synthesis",
    ] = "code"
    workspace: str
    prompt: str = Field(max_length=200000)
    output_schema: dict[str, Any] = Field(alias="schema")
    database: dict | None = None
    timeout: int = Field(ge=1, le=290)


def sandbox(workspace: Path, session: Path, attachments: Path):
    command = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--setenv",
        "PATH",
        "/usr/local/bin:/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/session",
        "--setenv",
        "CODEX_HOME",
        "/session/codex",
        "--setenv",
        "CLAUDE_CONFIG_DIR",
        "/session/claude",
        "--setenv",
        "DISABLE_AUTOUPDATER",
        "1",
        "--setenv",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "1",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "GIT_CONFIG_NOSYSTEM",
        "1",
        "--setenv",
        "GIT_CONFIG_COUNT",
        "2",
        "--setenv",
        "GIT_CONFIG_KEY_0",
        "safe.directory",
        "--setenv",
        "GIT_CONFIG_VALUE_0",
        "*",
        "--setenv",
        "GIT_CONFIG_KEY_1",
        "core.hooksPath",
        "--setenv",
        "GIT_CONFIG_VALUE_1",
        "/dev/null",
    ]
    for directory in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(directory).exists():
            command += ["--ro-bind", directory, directory]
    for file in (
        "/etc/ssl",
        "/etc/resolv.conf",
        "/etc/hosts",
        "/etc/nsswitch.conf",
        "/etc/passwd",
        "/etc/group",
    ):
        if Path(file).exists():
            command += ["--ro-bind", file, file]
    command += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(session),
        "/session",
        "--ro-bind",
        str(workspace),
        "/workspace",
        "--ro-bind",
        str(DATA / "git-cache"),
        str(DATA / "git-cache"),
        "--ro-bind",
        str(attachments),
        "/attachments",
        "--chdir",
        "/workspace",
    ]
    # Worktree metadata points at its original absolute path.
    command += ["--ro-bind", str(workspace), str(workspace)]
    return command


def verify_sandbox():
    result = subprocess.run(
        [
            "bwrap",
            "--ro-bind",
            "/",
            "/",
            "--tmpfs",
            "/tmp",
            "--unshare-pid",
            "--proc",
            "/proc",
            "/bin/sh",
            "-c",
            "! touch /usr/spechelper-readonly-probe 2>/dev/null",
        ],
        capture_output=True,
        timeout=10,
    )
    return result.returncode == 0


@app.get("/health", dependencies=[Depends(authorize)])
def health(agent: Literal["codex", "claude"] = "codex"):
    if not shutil.which(agent) or not shutil.which("bwrap"):
        return {"status": "ERROR", "account": "Incomplete runtime", "usage": "UNKNOWN"}
    if not verify_sandbox():
        return {
            "status": "ERROR",
            "account": "Isolation unavailable",
            "usage": "UNKNOWN",
        }
    return connection_status(CREDENTIALS, agent)


class LoginIn(BaseModel):
    attempt_id: uuid.UUID
    provider: Literal["codex", "claude"]


class LoginCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=4096)


@app.post("/auth/start", dependencies=[Depends(authorize)])
def start_login(payload: LoginIn):
    try:
        return logins.start(str(payload.attempt_id), payload.provider)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/auth/{attempt_id}", dependencies=[Depends(authorize)])
def login_status(attempt_id: uuid.UUID):
    return logins.get(str(attempt_id))


@app.post("/auth/{attempt_id}/code", dependencies=[Depends(authorize)])
def login_code(attempt_id: uuid.UUID, payload: LoginCodeIn):
    try:
        return logins.submit(str(attempt_id), payload.code.strip())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/auth/{attempt_id}/cancel", dependencies=[Depends(authorize)])
def cancel_login(attempt_id: uuid.UUID):
    return logins.cancel(str(attempt_id))


@app.post("/run", dependencies=[Depends(authorize)])
def run(payload: RunIn):
    request_id = str(payload.request_id)
    expected = DATA / "analysis-workspaces" / request_id
    if Path(payload.workspace) != expected or not expected.is_dir():
        raise HTTPException(422, "Invalid workspace")
    with guard:
        mutex = locks.setdefault(
            (request_id, str(payload.context_id or payload.request_id)), threading.Lock()
        )
    if not mutex.acquire(blocking=False):
        raise HTTPException(409, "Session busy")
    capability = None
    try:
        session = SESSIONS / request_id
        if payload.context_id and payload.context_id != payload.request_id:
            # Extra contexts must not sit inside the legacy primary directory:
            # that whole directory is mounted at /session for the primary CLI.
            session = SESSIONS / "contexts" / request_id / str(payload.context_id)
        agent_home = session / payload.agent
        agent_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Copy only the credential file, never administrator config, hooks, MCP servers or rules.
        credential_root = credential_directory(CREDENTIALS, payload.agent)
        names = ["auth.json"] if payload.agent == "codex" else [".credentials.json", ".claude.json"]
        credential_snapshot = None
        for name in names:
            auth = credential_root / name
            if auth.is_file():
                shutil.copyfile(auth, agent_home / name)
                (agent_home / name).chmod(0o600)
                if name in {"auth.json", ".credentials.json"}:
                    credential_snapshot = (name, (agent_home / name).read_bytes())
        schema = session / "schema.json"
        schema.write_text(json.dumps(payload.output_schema))
        output = session / "result.json"
        output.unlink(missing_ok=True)
        attachments = DATA / "requests" / request_id / "attachments"
        # Backend creates this folder before launch; runtime data volume is read-only.
        if not attachments.is_dir():
            raise HTTPException(422, "Attachments directory missing")
        user_prompt = payload.prompt
        if payload.database:
            capability = secrets.token_urlsafe(32)
            capabilities[capability] = {
                "config": payload.database,
                "expires": time.monotonic() + payload.timeout,
            }
            user_prompt += (
                "\nA read-only database is available through POST http://127.0.0.1:8090/query/"
                + capability
                + ' with JSON {"sql":"SELECT ..."}. Use curl if needed. Results are limited to 200 rows. No database credentials are provided.'
            )
        cli = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "--skip-git-repo-check",
            "--model",
            os.environ.get("CODEX_MODEL", "gpt-6-luna"),
            "--output-schema",
            "/session/schema.json",
            "--output-last-message",
            "/session/result.json",
            "-c",
            'approval_policy="never"',
            "-c",
            # Bubblewrap above enforces the read-only boundary. Codex's nested
            # sandbox cannot create another UID namespace after capabilities
            # have been dropped; run its tools inside our existing isolation.
            'sandbox_mode="danger-full-access"',
            "-c",
            'model_reasoning_effort="low"'
            if payload.phase == "understanding"
            else 'model_reasoning_effort="medium"',
        ]
        if payload.agent == "claude":
            cli = [
                "claude",
                "--print",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(payload.output_schema),
                "--permission-mode",
                "dontAsk",
                "--tools",
                "Read,Glob,Grep,Bash",
                "--allowedTools",
                "Read,Glob,Grep,Bash",
                "--disallowedTools",
                "Edit,Write,NotebookEdit,Bash(git push *)",
                "--setting-sources",
                "user",
                "--settings",
                '{"disableAllHooks":true}',
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--disable-slash-commands",
                "--no-chrome",
            ]
            if payload.session_id:
                cli += ["--resume", str(payload.session_id)]
            else:
                cli += ["--session-id", str(uuid.uuid4())]
        elif payload.session_id:
            cli += ["resume", str(payload.session_id), "-"]
        else:
            cli += ["-"]
        command = sandbox(expected, session, attachments) + cli
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        try:
            stdout, _ = process.communicate(user_prompt.encode(), timeout=payload.timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, _ = process.communicate()
            timed_out = True
        if credential_snapshot:
            name, original = credential_snapshot
            try:
                publish_refresh(
                    CREDENTIALS, payload.agent, original, (agent_home / name).read_bytes()
                )
            except OSError:
                pass  # Keep a completed analysis even if credential storage becomes unavailable.
        session_id = str(payload.session_id) if payload.session_id else None
        usage = {}
        if payload.agent == "claude" and not timed_out:
            try:
                result = json.loads(stdout)
                if (
                    result.get("is_error")
                    or not result.get("structured_output")
                    or process.returncode
                ):
                    return {"failure": classify_failure(stdout), "usage": result.get("usage", {})}
                return {
                    "output": result["structured_output"],
                    "session_id": result["session_id"],
                    "usage": result.get("usage", {}),
                    "elapsed": round(time.monotonic() - started, 2),
                }
            except (ValueError, KeyError):
                return {"failure": {"kind": "ERROR"}}
        for line in stdout.decode(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                session_id = event.get("thread_id")
            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})
        if timed_out:
            failure = classify_failure(stdout)
            if failure["kind"] in {"QUOTA_EXHAUSTED", "BUSY"}:
                return {"failure": failure}
            return {"timed_out": True, "session_id": session_id, "usage": usage}
        if process.returncode or not output.exists() or not session_id:
            return {"failure": classify_failure(stdout)}
        try:
            result = json.loads(output.read_text())
        except json.JSONDecodeError:
            raise HTTPException(502, "Invalid AI response")
        return {
            "output": result,
            "session_id": session_id,
            "usage": usage,
            "elapsed": round(time.monotonic() - started, 2),
        }
    finally:
        if capability:
            capabilities.pop(capability, None)
        mutex.release()


def classify_failure(stdout):
    """Interpret CLI error envelopes only. Never return raw provider output."""
    errors = []
    retry_seconds = None
    for line in stdout.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if event.get("type") not in {"error", "turn.failed"} and not event.get("is_error"):
            continue
        detail = event.get("error", event)
        errors.append(json.dumps(detail, ensure_ascii=False).lower())
        if isinstance(detail, dict) and isinstance(detail.get("retry_after"), (int, float)):
            retry_seconds = min(max(int(detail["retry_after"]), 1), 3600)
    text = " ".join(errors).replace("’", "'")
    if any(
        term in text
        for term in (
            "usage_limit_reached",
            "insufficient_quota",
            "quota_exceeded",
            "usage limit",
            "you've hit your limit",
            "you have hit your limit",
        )
    ):
        return {"kind": "QUOTA_EXHAUSTED"}
    if any(
        term in text for term in ("rate_limit", "rate limit", "overloaded", "too many requests")
    ):
        return {"kind": "BUSY", "retry_seconds": retry_seconds}
    return {"kind": "ERROR"}


class QueryIn(BaseModel):
    sql: str = Field(min_length=1, max_length=20000)


@app.post("/query/{capability}")
def database_query(capability: str, payload: QueryIn):
    connection = capabilities.get(capability)
    if not connection or connection["expires"] < time.monotonic():
        raise HTTPException(403, "Access expired or missing")
    try:
        return query(connection["config"], payload.sql)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
