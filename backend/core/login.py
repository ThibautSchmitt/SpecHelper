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
from urllib.parse import urlsplit

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
ACTIVE = {"STARTING", "AWAITING_USER"}
PROVIDERS = {"github": "GitHub", "codex": "ChatGPT", "claude": "Claude"}
ALLOWED_HOSTS = {
    "github": {"github.com"},
    "codex": {"auth.openai.com"},
    "claude": {"claude.ai", "claude.com", "console.anthropic.com", "platform.claude.com"},
}


def browser_details(provider, output, opened_url=""):
    clean = ANSI.sub("", output).replace("\r", "\n")
    candidates = ([opened_url] if opened_url else []) + re.findall(r"https://[^\s<>\"\x1b]+", clean)
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
        "input_required": provider == "claude" and bool(url),
    }


class TerminalLogin:
    def __init__(self, provider, on_complete, on_update=None, ttl=900, on_output=None):
        if provider not in PROVIDERS:
            raise ValueError("Unknown provider")
        self.provider, self.on_complete, self.on_update = provider, on_complete, on_update
        self.ttl = ttl
        self.on_output = on_output
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
            self.provider != "claude"
            or not self.state["input_required"]
            or self.state["status"] not in ACTIVE
        ):
            raise ValueError("No confirmation code is expected")
        if not re.fullmatch(r"[A-Za-z0-9_.#/+~=-]{1,4096}", code):
            raise ValueError("Invalid confirmation code")
        with self.mutex:
            if self.terminal is None:
                raise ValueError("The connection has ended")
            os.write(self.terminal, code.encode() + b"\n")
            self.update(input_required=False, message="Verifying connection…")

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="login-" + self.provider).start()

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix="spechelper-login-") as temp:
                home = Path(temp)
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
                            message="Complete sign-in on the website for "
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
                if self.process.returncode != 0:
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
