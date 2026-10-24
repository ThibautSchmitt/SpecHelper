"""Internal runtime. Its API is never published by Compose."""

import contextlib
import json
import os
import secrets
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.control import control_token
from core.postgres import query

from .auth import (
    Logins,
    claude_metadata,
    connection_status,
    credential_directory,
    identity_root,
    subscription_credentials,
)
from .broker import Broker
from .context_resources import ResourceReads, mount_resources, validated_resources
from .quota import rollout_windows
from .vault import read as read_credential
from .vault import seal as seal_credentials


@contextlib.asynccontextmanager
async def lifespan(application):
    seal_credentials(CREDENTIALS)
    seal_credentials(SESSIONS, validate_json=False)
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
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


class ContextResource(BaseModel):
    version_id: uuid.UUID
    path: str = Field(min_length=1, max_length=256)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunIn(BaseModel):
    request_id: uuid.UUID
    context_id: uuid.UUID | None = None
    independent_context: bool = False
    session_id: uuid.UUID | None = None
    agent: Literal["codex", "claude"] = "codex"
    identity_id: uuid.UUID | None = None
    model: str = Field(default="", max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$|^$")
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
    context_dir: str | None = None
    context_resources: list[ContextResource] = Field(default_factory=list, max_length=64)
    timeout: int = Field(ge=1, le=290)


def sandbox(workspace: Path, session: Path, attachments: Path, context_resources=(), broker=None):
    command = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-net",
        "--cap-drop",
        "ALL",
        "--cap-add",
        "CAP_SETUID",
        "--cap-add",
        "CAP_SETGID",
        "--cap-add",
        "CAP_SETPCAP",
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
        "--perms",
        "1777",
        "--size",
        "67108864",
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
    command += mount_resources(context_resources)
    command += ["--chmod", "0755", "/etc", "--chmod", "1777", "/tmp"]
    # Bubblewrap creates synthetic parent directories with mode0700. Make only
    # those empty mount ancestors traversable for the non-root analysis identity.
    parents = set(workspace.parents) | set((DATA / "git-cache").parents)
    for parent in sorted(parents, key=lambda value: len(value.parts)):
        if parent not in {
            Path("/"),
            Path("/tmp"),
            Path("/usr"),
            Path("/bin"),
            Path("/lib"),
            Path("/lib64"),
        }:
            command += ["--chmod", "0755", str(parent)]
    if broker:
        command += [
            "--ro-bind",
            str(broker.path),
            "/broker.sock",
            "--ro-bind",
            str(Path(__file__).with_name("relay.py")),
            "/bootstrap.py",
        ]
        command += [
            "--setenv",
            "ANTHROPIC_BASE_URL",
            "http://127.0.0.1:8090/claude",
            "--setenv",
            "CLAUDE_CODE_OAUTH_TOKEN",
            broker.token,
            "--setenv",
            "SPECHELPER_PROVIDER_TOKEN",
            broker.token,
        ]
    command += ["--ro-bind", str(Path(__file__).with_name("restrict.py")), "/restrict.py"]
    command += [
        "setpriv",
        "--reuid=10001",
        "--regid=10001",
        "--clear-groups",
        "--bounding-set=-all",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--no-new-privs",
        "python3",
        "/restrict.py",
    ]
    if broker:
        command += ["python3", "/bootstrap.py"]
    return command


SESSION_BYTES = 128 * 1024 * 1024


def session_size(session):
    total = 0
    for index, item in enumerate(session.rglob("*")):
        if index > 10000:
            return SESSION_BYTES + 1
        if not item.is_symlink() and item.is_file():
            total += item.stat().st_size
    return total


def scrub_session(session, root):
    """Remove known historical CLI credentials from this context before exposing it again."""
    if session_size(session) > SESSION_BYTES:
        raise HTTPException(422, "Session storage limit exceeded")
    private = []
    for provider, filename, section in (
        ("codex", "auth.json", "tokens"),
        ("claude", ".credentials.json", "claudeAiOauth"),
    ):
        for path in (
            credential_directory(root, provider) / filename,
            session / provider / filename,
        ):
            try:
                values = json.loads(read_credential(path)).get(section, {})
                private += [
                    value.encode()
                    for key, value in values.items()
                    if key
                    in {"access_token", "refresh_token", "id_token", "accessToken", "refreshToken"}
                    and isinstance(value, str)
                    and len(value) >= 8
                ]
            except (OSError, ValueError, AttributeError):
                continue
    for item in session.rglob("*"):
        if item.is_symlink() or not item.is_file():
            continue
        content = item.read_bytes()
        cleaned = content
        for secret in private:
            cleaned = cleaned.replace(secret, b"[REDACTED]")
        if cleaned != content:
            item.write_bytes(cleaned)


def watch_session(session, process, stop):
    while not stop.wait(0.5):
        try:
            if session_size(session) > SESSION_BYTES:
                os.killpg(process.pid, signal.SIGKILL)
                return
        except (OSError, AttributeError):
            return


def verify_sandbox():
    """Reject execution unless real non-root identity, network and capability isolation work."""
    try:
        result = subprocess.run(
            [
                "bwrap",
                "--ro-bind",
                "/",
                "/",
                "--tmpfs",
                "/tmp",
                "--unshare-pid",
                "--unshare-net",
                "--proc",
                "/proc",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CAP_SETUID",
                "--cap-add",
                "CAP_SETGID",
                "--cap-add",
                "CAP_SETPCAP",
                "setpriv",
                "--reuid=10001",
                "--regid=10001",
                "--clear-groups",
                "--bounding-set=-all",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "python3",
                "-c",
                "import os,pathlib,socket; assert os.getuid()==10001 and os.getgid()==10001; assert 'CapEff:\\t0000000000000000' in pathlib.Path('/proc/self/status').read_text(); s=socket.socket(); s.settimeout(.2); assert s.connect_ex(('1.1.1.1',443)) != 0",
            ],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@app.get("/health", dependencies=[Depends(authorize)])
def health(
    agent: Literal["codex", "claude"] = "codex",
    identity_id: uuid.UUID | None = None,
    quota: bool = False,
):
    if not shutil.which(agent) or not shutil.which("bwrap"):
        return {"status": "ERROR", "account": "Incomplete runtime", "usage": "UNKNOWN"}
    if not verify_sandbox():
        return {
            "status": "ERROR",
            "account": "Isolation unavailable",
            "usage": "UNKNOWN",
        }
    return connection_status(identity_root(CREDENTIALS, identity_id), agent, include_quota=quota)


@app.get("/models", dependencies=[Depends(authorize)])
def models(agent: Literal["codex", "claude"], identity_id: uuid.UUID | None = None):
    from .model_discovery import discover

    return discover(identity_root(CREDENTIALS, identity_id), agent)


class LoginIn(BaseModel):
    attempt_id: uuid.UUID
    provider: Literal["codex", "claude"]
    identity_id: uuid.UUID | None = None


class LoginCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=4096)


@app.post("/auth/start", dependencies=[Depends(authorize)])
def start_login(payload: LoginIn):
    try:
        return logins.start(
            str(payload.attempt_id),
            payload.provider,
            str(payload.identity_id) if payload.identity_id else None,
        )
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
    try:
        resources = validated_resources(
            DATA, request_id, payload.context_dir, payload.context_resources
        )
    except ValueError as exc:
        raise HTTPException(422, "Invalid context resources") from exc
    with guard:
        mutex = locks.setdefault(
            (request_id, str(payload.context_id or payload.request_id)), threading.Lock()
        )
    if not mutex.acquire(blocking=False):
        raise HTTPException(409, "Session busy")
    capability = None
    broker = None
    reads = None
    context_observation = {"context_usage": [], "context_audit": "unavailable"}
    try:
        session = SESSIONS / request_id
        if payload.independent_context or (
            payload.context_id and payload.context_id != payload.request_id
        ):
            # Extra contexts must not sit inside the legacy primary directory:
            # that whole directory is mounted at /session for the primary CLI.
            session = (
                SESSIONS / "contexts" / request_id / str(payload.context_id or payload.request_id)
            )
        if session.is_symlink() or any(
            parent.is_symlink() for parent in session.parents if parent != Path("/")
        ):
            raise HTTPException(422, "Invalid session directory")
        agent_home = session / payload.agent
        if any((session / provider).is_symlink() for provider in ("codex", "claude")):
            raise HTTPException(422, "Invalid session directory")
        agent_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Real OAuth credentials never enter any analysis-readable filesystem or environment.
        root = identity_root(CREDENTIALS, payload.identity_id)
        credential_root = credential_directory(root, payload.agent)
        if not subscription_credentials(credential_root, payload.agent):
            return {"failure": {"kind": "AUTH_ERROR"}, **context_observation}
        credential_name = "auth.json" if payload.agent == "codex" else ".credentials.json"
        credential_data = json.loads(read_credential(credential_root / credential_name))
        broker = Broker(
            payload.agent,
            credential_data,
            payload.timeout,
            database=(lambda sql: query(payload.database, sql, minimize=True))
            if payload.database
            else None,
        )
        broker.__enter__()
        context_observation["database_checks"] = broker.database_checks
        scrub_session(session, root)
        # Remove all legacy credential copies, including an alternate provider used in this context.
        for provider in ("codex", "claude"):
            for name in ("auth.json", ".credentials.json", ".claude.json"):
                (session / provider / name).unlink(missing_ok=True)
        if payload.agent == "codex":
            auth = {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": broker.token,
                    "refresh_token": "broker-only",
                    "account_id": "spechelper-scoped",
                    "id_token": "",
                },
                "last_refresh": datetime.now(UTC).isoformat(),
            }
            (agent_home / "auth.json").write_text(json.dumps(auth))
            (agent_home / "auth.json").chmod(0o600)
        elif (credential_root / ".claude.json").is_file():
            (agent_home / ".claude.json").write_text(
                json.dumps(claude_metadata(read_credential(credential_root / ".claude.json")))
            )
        schema = session / "schema.json"
        schema.unlink(missing_ok=True)
        schema.write_text(json.dumps(payload.output_schema))
        output = session / "result.json"
        output.unlink(missing_ok=True)
        attachments = DATA / "requests" / request_id / "attachments"
        # Backend creates this folder before launch; runtime data volume is read-only.
        if not attachments.is_dir():
            raise HTTPException(422, "Attachments directory missing")
        user_prompt = payload.prompt
        if payload.database:
            user_prompt += '\nA read-only database is available through POST http://127.0.0.1:8090/database with JSON {"sql":"SELECT ..."}. Prefer existence checks, counts and grouped states. Previews expose at most 20 minimized rows; sensitive-looking fields are masked. Each query returns a service-generated query_id and checked_at timestamp: cite that query_id as SQL evidence. No database credentials are provided.'
        cli = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "--skip-git-repo-check",
            "--model",
            payload.model or os.environ.get("CODEX_MODEL", "gpt-6-luna"),
            "--output-schema",
            "/session/schema.json",
            "--output-last-message",
            "/session/result.json",
            "-c",
            'chatgpt_base_url="http://127.0.0.1:8090"',
            "-c",
            'model_provider="spechelper"',
            "-c",
            'model_providers.spechelper.name="SpecHelper provider relay"',
            "-c",
            'model_providers.spechelper.base_url="http://127.0.0.1:8090/codex"',
            "-c",
            'model_providers.spechelper.wire_api="responses"',
            "-c",
            "model_providers.spechelper.requires_openai_auth=false",
            "-c",
            'model_providers.spechelper.env_key="SPECHELPER_PROVIDER_TOKEN"',
            "-c",
            "model_providers.spechelper.supports_websockets=false",
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
            if payload.model:
                cli += ["--model", payload.model]
        elif payload.session_id:
            cli += ["resume", str(payload.session_id), "-"]
        else:
            cli += ["-"]
        if os.geteuid() == 0:
            for directory in [session, *session.rglob("*")]:
                if not directory.is_symlink():
                    os.chown(directory, 10001, 10001)
        command = sandbox(expected, session, attachments, resources, broker) + cli
        started = time.monotonic()
        observed_after = datetime.now(UTC)
        reads = ResourceReads(resources)
        captured = tempfile.TemporaryFile()
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=captured,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        monitor_stop = threading.Event()
        monitor = threading.Thread(
            target=watch_session, args=(session, process, monitor_stop), daemon=True
        )
        monitor.start()
        try:
            stdout, _ = process.communicate(user_prompt.encode(), timeout=payload.timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, _ = process.communicate()
            timed_out = True
        finally:
            monitor_stop.set()
            monitor.join(timeout=1)
        if stdout is None:
            captured.seek(0)
            stdout = captured.read(64 * 1024 * 1024 + 1)
        captured.close()
        if len(stdout) > 64 * 1024 * 1024:
            return {"failure": {"kind": "ERROR"}, **context_observation}
        context_observation = reads.finish()
        context_observation["database_checks"] = broker.database_checks
        broker.observe_commands(stdout)
        broker.observe_session(session)
        session_id = str(payload.session_id) if payload.session_id else None
        usage = {}
        if payload.agent == "claude" and not timed_out:
            try:
                result = broker.redact(json.loads(stdout))
                if (
                    result.get("is_error")
                    or not result.get("structured_output")
                    or process.returncode
                ):
                    return {
                        "failure": classify_failure(stdout),
                        "usage": result.get("usage", {}),
                        **context_observation,
                    }
                return {
                    "output": result["structured_output"],
                    **context_observation,
                    "session_id": result["session_id"],
                    "usage": result.get("usage", {}),
                    "elapsed": round(time.monotonic() - started, 2),
                    "model": next(
                        iter(result.get("modelUsage", {})), payload.model or "runtime-default"
                    ),
                }
            except (ValueError, KeyError):
                return {"failure": {"kind": "ERROR"}, **context_observation}
        for line in stdout.decode(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "thread.started":
                session_id = event.get("thread_id")
            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})
        quota_windows = rollout_windows(agent_home, session_id, observed_after)
        if timed_out:
            failure = classify_failure(stdout)
            if failure["kind"] in {"QUOTA_EXHAUSTED", "BUSY"}:
                return {
                    "failure": {**failure, "quota_windows": quota_windows},
                    **context_observation,
                }
            return {
                "timed_out": True,
                "session_id": session_id,
                "usage": usage,
                **context_observation,
            }
        if process.returncode or not output.exists() or not session_id:
            return {
                "failure": {**classify_failure(stdout), "quota_windows": quota_windows},
                **context_observation,
            }
        try:
            descriptor = os.open(output, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 2 * 1024 * 1024:
                    raise HTTPException(502, "Invalid AI response")
                result = broker.redact(json.loads(stream.read(2 * 1024 * 1024 + 1)))
        except (OSError, ValueError):
            raise HTTPException(502, "Invalid AI response")
        return {
            "output": result,
            **context_observation,
            "session_id": session_id,
            "usage": usage,
            "elapsed": round(time.monotonic() - started, 2),
            "model": payload.model or os.environ.get("CODEX_MODEL", "gpt-6-luna"),
            "quota_windows": quota_windows,
        }
    finally:
        if reads is not None:
            reads.close()
        if broker is not None:
            broker.__exit__(None, None, None)
        if capability:
            capabilities.pop(capability, None)
        mutex.release()


def classify_failure(stdout):
    """Interpret CLI error envelopes only. Never return raw provider output."""
    errors = []
    retry_seconds = None
    authentication_error = False
    for line in stdout.decode(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if event.get("type") not in {"error", "turn.failed"} and not event.get("is_error"):
            continue
        authentication_error |= event.get("api_error_status") == 401
        detail = event.get("error", event)
        errors.append(json.dumps(detail, ensure_ascii=False).lower())
        if isinstance(detail, dict) and isinstance(detail.get("retry_after"), (int, float)):
            retry_seconds = min(max(int(detail["retry_after"]), 1), 3600)
    text = " ".join(errors).replace("’", "'")
    if authentication_error:
        return {"kind": "AUTH_ERROR"}
    if any(
        term in text
        for term in (
            "model_not_found",
            "issue with the selected model",
            "unsupported model",
            "model is not available",
            "invalid model",
            "model does not exist",
        )
    ):
        return {"kind": "MODEL_UNAVAILABLE"}
    if any(
        term in text
        for term in (
            "authentication_error",
            "invalid_grant",
            "unauthorized",
            "login required",
            "not logged in",
            "token expired",
        )
    ):
        return {"kind": "AUTH_ERROR"}
    if any(
        term in text
        for term in (
            "usage_limit_reached",
            "credits_required",
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
        return query(connection["config"], payload.sql, minimize=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
