"""Read-only Docker/API sampling. Output contains no container environment or CLI arguments."""

import argparse
import json
import platform
import re
import statistics
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def command(*arguments):
    return subprocess.check_output(arguments, text=True, timeout=20).strip()


def memory_bytes(value):
    units = {
        "B": 1,
        "kB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
    }
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            return round(float(value[: -len(unit)]) * units[unit])
    raise ValueError("Unknown Docker memory unit")


def summarize(samples):
    services = {}
    for name in sorted({row["service"] for sample in samples for row in sample["services"]}):
        rows = [row for sample in samples for row in sample["services"] if row["service"] == name]
        services[name] = {
            "samples": len(rows),
            "memory_mean_bytes": round(statistics.mean(row["memory_bytes"] for row in rows)),
            "memory_peak_bytes": max(row["memory_bytes"] for row in rows),
            "cpu_mean_percent": round(statistics.mean(row["cpu_percent"] for row in rows), 3),
            "cpu_peak_percent": max(row["cpu_percent"] for row in rows),
            "pid_threads_peak": max(row["pid_threads"] for row in rows),
        }
    return {
        "services": services,
        "sampled_total_memory_peak_bytes": max(
            sum(r["memory_bytes"] for r in s["services"]) for s in samples
        ),
    }


def sample(project, api_url):
    identifiers = command(
        "docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + project
    ).split()
    if not identifiers:
        raise ValueError("No running containers for this Compose project")
    containers = json.loads(command("docker", "inspect", *identifiers))
    identities = {
        row["Id"][:12]: row["Config"]["Labels"].get("com.docker.compose.service", row["Name"])
        for row in containers
    }
    raw = command("docker", "stats", "--no-stream", "--format", "{{json .}}", *identities)
    services = []
    for line in raw.splitlines():
        row = json.loads(line)
        services.append(
            {
                "service": identities[row["ID"][:12]],
                "memory_bytes": memory_bytes(row["MemUsage"].split(" / ")[0]),
                "cpu_percent": float(row["CPUPerc"].removesuffix("%")),
                "pid_threads": int(row["PIDs"]),
            }
        )
    latency = None
    error = None
    if api_url:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(api_url, timeout=10) as response:
                response.read(2_000_001)
                latency = time.perf_counter() - started
        except (OSError, ValueError) as exc:
            error = type(exc).__name__
    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "services": services,
        "api_seconds": latency,
        "api_error": error,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="spechelper")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--api-url")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.samples <= 3600 or not 0 <= args.interval <= 3600:
        parser.error("Use 1–3600 samples and a nonnegative bounded interval")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", args.project):
        parser.error("Invalid Compose project name")
    if args.api_url:
        url = urlsplit(args.api_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            parser.error("Use an HTTP(S) health URL without embedded credentials")
    info = json.loads(command("docker", "info", "--format", "{{json .}}"))
    result = {
        "phase": args.phase,
        "project": args.project,
        "host": {"platform": platform.system(), "machine": platform.machine()},
        "docker": {key: info.get(key) for key in ("NCPU", "MemTotal", "ServerVersion", "Driver")},
        "limits": [
            "Docker PIDs include threads, not only processes",
            "Sampled peaks can miss spikes between samples",
            "CPU percentages are Docker core-relative, not normalized to the whole host",
            "API timings measure reads only, not AI completion latency",
        ],
        "samples": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for index in range(args.samples):
        result["samples"].append(sample(args.project, args.api_url))
        result["summary"] = summarize(result["samples"])
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        if index + 1 < args.samples:
            time.sleep(args.interval)
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
