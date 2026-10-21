"""Detect orphaned Bubblewrap children. Run with Compose's init and PID limit."""

import time
from pathlib import Path

from runtime.server import verify_sandbox


def zombies():
    count = 0
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            # comm is parenthesized and may contain spaces.
            state = path.read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            continue
        count += state == "Z"
    return count


def main():
    before = zombies()
    for _ in range(300):
        assert verify_sandbox(), "Isolation unavailable before 300 repeated probes"
    deadline = time.monotonic() + 2
    while zombies() > before and time.monotonic() < deadline:
        time.sleep(0.05)
    after = zombies()
    assert after <= before, f"Unreaped children: {before} -> {after}"
    print({"sandbox_probes": 300, "zombies_before": before, "zombies_after": after})


if __name__ == "__main__":
    main()
