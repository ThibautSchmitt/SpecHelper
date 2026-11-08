"""Run inside Linux runtime: process names/resources only, never arguments or environment."""

import json
from pathlib import Path


def snapshot(root=Path("/proc"), cgroup=Path("/sys/fs/cgroup")):
    processes = []
    for directory in root.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            status = dict(
                line.split(":", 1)
                for line in (directory / "status").read_text().splitlines()
                if ":" in line
            )
            processes.append(
                {
                    "pid": int(directory.name),
                    "ppid": int(status["PPid"]),
                    "name": status["Name"].strip(),
                    "state": status["State"].split()[0],
                    "rss_bytes": int(status.get("VmRSS", "0 kB").split()[0]) * 1024,
                    "threads": int(status["Threads"]),
                }
            )
        except (OSError, KeyError, ValueError):
            continue  # exited between listing and observation
    counters = {}
    for name in ["memory.events", "memory.current", "memory.peak", "pids.events", "pids.current"]:
        try:
            counters[name] = (cgroup / name).read_text().strip()
        except OSError:
            counters[name] = None
    return {
        "processes": processes,
        "zombies": sum(row["state"] == "Z" for row in processes),
        "cgroup": counters,
        "limits": "Transient probe processes are included; RSS sums double count shared pages.",
    }


if __name__ == "__main__":
    print(json.dumps(snapshot()))
