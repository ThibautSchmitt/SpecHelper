"""Read optional official quota snapshots from the current Codex rollout only."""

import json
import math
import uuid
from datetime import UTC, datetime


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
