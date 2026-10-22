"""Read official account usage and invocation-local quota snapshots without inference probes."""

import json
import math
import queue
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime


def app_server_windows(value):
    """Translate the installed app-server's camelCase quota protocol."""
    if not isinstance(value, dict):
        return {}
    snapshot = value.get("rateLimits", {})
    if not isinstance(snapshot, dict):
        return {}
    return codex_windows(
        {
            name: {
                "window_minutes": item.get("windowDurationMins"),
                "used_percent": item.get("usedPercent"),
                "resets_at": item.get("resetsAt"),
            }
            for name in ("primary", "secondary")
            if isinstance(item := snapshot.get(name), dict)
        }
    )


def read_codex_quota(directory, env, timeout=8):
    """Read account usage without creating a thread, submitting a turn or spending credits."""
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
                raise TimeoutError("Quota read timed out")
            try:
                value = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("Quota read timed out") from exc
            if value is None:
                raise ValueError("Quota reader stopped")
            if isinstance(value, dict) and value.get("id") == identifier:
                if "error" in value or not isinstance(value.get("result"), dict):
                    raise ValueError("Quota read failed")
                return value["result"]
        raise ValueError("Too many quota notifications")

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "spechelper", "version": "1.8"}},
            }
        )
        response(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "account/rateLimits/read", "params": None})
        return response(2)
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


def codex_windows(snapshot):
    """Protocol RateLimitSnapshot: durations and percentages are never inferred."""
    if not isinstance(snapshot, dict):
        return {}
    windows = {}
    for key in ("primary", "secondary"):
        item = snapshot.get(key)
        if not isinstance(item, dict):
            continue
        minutes, used = item.get("window_minutes"), item.get("used_percent")
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            continue
        name = "weekly" if minutes == 10080 else "session" if 0 < minutes < 1440 else None
        if (
            name is None
            or not isinstance(used, (int, float))
            or isinstance(used, bool)
            or not math.isfinite(used)
            or not 0 <= used <= 100
        ):
            continue
        window = {"used_percent": used, "exhausted": used >= 100}
        reset = item.get("resets_at")
        if isinstance(reset, int) and not isinstance(reset, bool) and reset > 0:
            try:
                window["resets_at"] = datetime.fromtimestamp(reset, UTC).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
        windows[name] = window
    return windows


def rollout_windows(agent_home, session_id, observed_after):
    """No probes: inspect bounded bytes emitted by this invocation's own CLI session."""
    try:
        identifier = str(uuid.UUID(str(session_id)))
    except (ValueError, TypeError, AttributeError):
        return {}
    directory = agent_home / "sessions"
    windows = {}
    for index, path in enumerate(directory.rglob("*" + identifier + ".jsonl")):
        if index >= 8:
            break
        try:
            if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
                continue
            with path.open("rb") as stream:
                size = path.stat().st_size
                stream.seek(max(0, size - 2 * 1024 * 1024))
                if stream.tell():
                    stream.readline()
                for line in stream:
                    if len(line) > 256000:
                        continue
                    try:
                        event = json.loads(line)
                        timestamp = datetime.fromisoformat(
                            event.get("timestamp", "").replace("Z", "+00:00")
                        )
                        payload = event.get("payload", {})
                        if (
                            timestamp.tzinfo is None
                            or timestamp < observed_after
                            or event.get("type") != "event_msg"
                            or not isinstance(payload, dict)
                            or payload.get("type") != "token_count"
                        ):
                            continue
                        windows.update(codex_windows(payload.get("rate_limits")))
                    except (ValueError, TypeError, AttributeError):
                        continue
        except OSError:
            continue
    return windows
