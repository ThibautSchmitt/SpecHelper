import json

import pytest
from scripts.evaluation import resource_probe as probe


def test_empty_project_has_an_actionable_read_only_failure(monkeypatch):
    commands = []

    def command(*args):
        commands.append(args)
        return ""

    monkeypatch.setattr(probe, "command", command)
    with pytest.raises(ValueError, match="No running"):
        probe.sample("empty", None)
    assert len(commands) == 1  # never executes unbounded docker stats


def test_only_whitelisted_metrics_leave_docker_inspection(monkeypatch):
    row = {
        "Id": "a" * 64,
        "Name": "fixture",
        "Config": {
            "Labels": {"com.docker.compose.service": "worker"},
            "Env": ["TOKEN=must-not-leak"],
        },
    }

    def command(*args):
        if args[1] == "ps":
            return row["Id"]
        if args[1] == "inspect":
            return json.dumps([row])
        return json.dumps(
            {"ID": "a" * 12, "MemUsage": "12MiB / 1GiB", "CPUPerc": "25.5%", "PIDs": "3"}
        )

    monkeypatch.setattr(probe, "command", command)
    result = probe.sample("fixture", None)
    assert "must-not-leak" not in json.dumps(result)
    assert result["services"] == [
        {"service": "worker", "memory_bytes": 12 * 1024**2, "cpu_percent": 25.5, "pid_threads": 3}
    ]
    assert probe.summarize([result])["sampled_total_memory_peak_bytes"] == 12 * 1024**2
