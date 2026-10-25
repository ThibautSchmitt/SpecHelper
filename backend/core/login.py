"""Turn official CLI browser logins into a small, safe UI protocol.

No raw terminal output, credentials, shell commands or arbitrary input reach the browser.
"""

import fcntl
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
ACTIVE = {"STARTING", "AWAITING_USER"}
PROVIDERS = {"github": "GitHub", "codex": "ChatGPT", "claude": "Claude", "antigravity": "Antigravity"}
ALLOWED_HOSTS = {
    "github": {"github.com"},
    "codex": {"auth.openai.com"},
    "claude": {"claude.ai", "claude.com", "console.anthropic.com", "platform.claude.com"},
    "antigravity": {"accounts.google.com"},
}


def browser_details(provider, output, opened_url=""):
    clean = ANSI.sub("", output).replace("\r", "\n")
    candidates = ([opened_url] if opened_url else []) + re.findall(r"https://[^\s<>\"\x1b]+", clean)
    if provider == "antigravity":
        # The pinned native SSH login renders its URL across terminal lines
        # instead of invoking BROWSER. Reassemble only contiguous URL fragments;
        # never publish the incomplete first line as an authorization link.
        lines = clean.splitlines()
        wrapped = []
        for index, line in enumerate(lines):
            start = re.search(r"https://accounts\.google\.com/[^\s<>\"\x1b]+", line)
            if not start:
                continue
            candidate = start.group()
            for continuation in lines[index + 1:]:
                fragment = continuation.strip()
                if not fragment:
                    continue
                if not re.fullmatch(r"[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", fragment):
                    break
                candidate += fragment
            wrapped.append(candidate)
        candidates = ([opened_url] if opened_url else []) + wrapped
    url = ""
    for candidate in candidates:
        candidate = candidate.rstrip(".)]")
        parsed = urlsplit(candidate)
        if (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS[provider]
            and not parsed.username
        ):
            if provider == "github" and parsed.path != "/login/device":
                continue
            if provider == "antigravity":
                query = parse_qs(parsed.query)
                required = ("client_id", "redirect_uri", "state", "code_challenge")
                if (
                    parsed.path not in {"/o/oauth2/auth", "/o/oauth2/v2/auth"}
                    or query.get("response_type") != ["code"]
                    or any(len(query.get(key, [])) != 1 or not query[key][0] for key in required)
                ):
                    continue
            url = candidate
            break
    code = ""
    if provider in {"github", "codex"}:
        found = re.search(r"\b[A-Z0-9]{4,5}-[A-Z0-9]{4,5}\b", clean)
        if found:
            code = found.group()
    return {
        "verification_uri": url,
        "user_code": code,
        "input_required": provider in {"claude", "antigravity"} and bool(url),
    }


class TerminalLogin:
    def __init__(self, provider, on_complete, on_update=None, ttl=900, on_output=None, completion_ready=None):
        if provider not in PROVIDERS:
            raise ValueError("Unknown provider")
        self.provider, self.on_complete, self.on_update = provider, on_complete, on_update
        self.ttl = ttl
        self.on_output = on_output
        self.completion_ready = completion_ready
        self.state = {
            "status": "STARTING",
            "verification_uri": "",
            "user_code": "",
            "input_required": False,
            "message": "Preparing connection…",
            "provider": provider,
        }
        self.mutex = threading.RLock()
        self.process = None
        self.terminal = None
        self.cancelled = threading.Event()

    def update(self, **changes):
        with self.mutex:
            if all(self.state.get(key) == value for key, value in changes.items()):
                return
            self.state.update(changes)
            state = self.state.copy()
        if self.on_update:
            self.on_update(state)

    def public(self):
        with self.mutex:
            return self.state.copy()

    def cancel(self):
        with self.mutex:
            if self.state["status"] in ACTIVE:
                self.cancelled.set()

    def submit(self, code):
        if (
            self.provider not in {"claude", "antigravity"}
            or not self.state["input_required"]
            or self.state["status"] not in ACTIVE
        ):
            raise ValueError("No confirmation code is expected")
        if not re.fullmatch(r"[A-Za-z0-9_.#/+~=-]{1,4096}", code):
            raise ValueError("Invalid confirmation code")
        with self.mutex:
            if self.terminal is None:
                raise ValueError("The connection has ended")
            # Antigravity's raw TUI treats LF as Ctrl-J, not Enter. Claude's
            # line-oriented login keeps its existing newline protocol.
            os.write(self.terminal, code.encode() + (b"\r" if self.provider == "antigravity" else b"\n"))
            self.update(input_required=False, message="Verifying connection…")

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="login-" + self.provider).start()

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix="spechelper-login-") as temp:
                home = Path(temp).resolve()
                for directory in ("codex", "claude", "github"):
                    (home / directory).mkdir(mode=0o700)
                helper = Path(__file__).with_name("login_browser.py")
                env = {
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "HOME": str(home),
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "TERM": "dumb",
                    "NO_COLOR": "1",
                    "BROWSER": str(helper),
                    "GH_BROWSER": str(helper),
                    "SPECHELPER_LOGIN_URL_FILE": str(home / "browser-url"),
                    "CODEX_HOME": str(home / "codex"),
                    "CLAUDE_CONFIG_DIR": str(home / "claude"),
                    "GH_CONFIG_DIR": str(home / "github"),
                    "DISABLE_AUTOUPDATER": "1",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                }
                commands = {
                    "antigravity": ["agy"],
                    "github": [
                        "gh",
                        "auth",
                        "login",
                        "--hostname",
                        "github.com",
                        "--git-protocol",
                        "https",
                        "--web",
                    ],
                    "codex": ["codex", "login", "--device-auth"],
                    "claude": ["claude", "auth", "login", "--claudeai"],
                }
                if self.provider == "antigravity":
                    # The official remote login uses Google's code callback. No
                    # developer keyring or initial inference prompt is available.
                    env.update(
                        DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent",
                        SSH_CONNECTION="127.0.0.1 12345 127.0.0.1 22",
                        XDG_CONFIG_HOME=str(home / ".config"),
                        XDG_CACHE_HOME=str(home / ".cache"),
                    )
                if not shutil.which(commands[self.provider][0]):
                    raise RuntimeError("Sign-in client unavailable")
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
                self.terminal = master
                try:
                    self.process = subprocess.Popen(
                        commands[self.provider],
                        stdin=subprocess.DEVNULL if self.provider == "github" else slave,
                        stdout=slave,
                        stderr=slave,
                        env=env,
                        cwd=home,
                        start_new_session=True,
                        close_fds=True,
                    )
                finally:
                    os.close(slave)
                deadline = time.monotonic() + self.ttl
                output = ""
                opened = False
                git_question_answered = False
                google_selected = False
                completed_while_running = False
                while self.process.poll() is None:
                    if self.cancelled.is_set() or time.monotonic() >= deadline:
                        os.killpg(self.process.pid, signal.SIGKILL)
                        self.process.wait()
                        self.update(
                            status="CANCELLED" if self.cancelled.is_set() else "EXPIRED",
                            message="Connection cancelled."
                            if self.cancelled.is_set()
                            else "The connection timed out. Try again.",
                            input_required=False,
                        )
                        return
                    if select.select([master], [], [], 0.2)[0]:
                        try:
                            chunk = os.read(master, 8192)
                        except OSError:
                            chunk = b""
                        output = (output + chunk.decode(errors="replace"))[-65536:]
                        if b"\x1b[6n" in chunk:
                            os.write(master, b"\x1b[1;1R")
                        if self.on_output:
                            self.on_output(chunk.decode(errors="replace"))
                    if self.provider == "antigravity" and not google_selected:
                        clean = ANSI.sub("", output)
                        if "Select login method:" in clean and "> 1. Google OAuth" in clean:
                            # This is the method the user chose in SpecHelper;
                            # never select GCP billing or accept provider terms.
                            os.write(master, b"\r")
                            google_selected = True
                    if self.provider == "antigravity" and "Got an error:" in ANSI.sub("", output):
                        raise RuntimeError("The native Google authorization failed")
                    urlfile = home / "browser-url"
                    details = browser_details(
                        self.provider, output, urlfile.read_text() if urlfile.exists() else ""
                    )
                    if details["verification_uri"]:
                        # Don't re-enable the code form after a submitted confirmation.
                        if self.state["verification_uri"] and not self.state["input_required"]:
                            details["input_required"] = False
                        self.update(
                            status="AWAITING_USER",
                            message="Verifying connection…"
                            if self.provider == "antigravity" and self.state["verification_uri"] and not self.state["input_required"]
                            else "Complete sign-in on the website for "
                            + PROVIDERS[self.provider]
                            + ".",
                            **details,
                        )
                    if self.provider == "github" and not opened and "Press Enter" in output:
                        os.write(master, b"\r")
                        opened = True
                    if (
                        self.provider == "github"
                        and not git_question_answered
                        and "Authenticate Git" in output
                    ):
                        os.write(master, b"n\r")
                        git_question_answered = True
                    if self.completion_ready and self.completion_ready(home):
                        # Interactive agy stays open after login. Stop this exact
                        # auth process before any chat can run, then seal its token.
                        os.killpg(self.process.pid, signal.SIGKILL)
                        self.process.wait()
                        completed_while_running = True
                        break
                if self.process.returncode != 0 and not completed_while_running:
                    raise RuntimeError("Connection refused")
                if self.cancelled.is_set():
                    self.update(
                        status="CANCELLED", input_required=False, message="Connection cancelled."
                    )
                    return
                with self.mutex:
                    if self.cancelled.is_set():
                        self.update(
                            status="CANCELLED",
                            input_required=False,
                            message="Connection cancelled.",
                        )
                        return
                    account = self.on_complete(home, env) or {}
                    self.update(
                        status="CONNECTED",
                        input_required=False,
                        message="Connection successful.",
                        **account,
                    )
        except Exception:
            self.update(
                status="ERROR",
                input_required=False,
                message="Sign-in did not complete. Retry or check your subscription and service access.",
            )
        finally:
            with self.mutex:
                if self.process and self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait()
                if self.terminal is not None:
                    os.close(self.terminal)
                    self.terminal = None
