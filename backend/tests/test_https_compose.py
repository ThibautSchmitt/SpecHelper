"""Exercise Compose's real merge/interpolation without starting services or reading .env."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def docker():
    executable = shutil.which("docker")
    if not executable:
        pytest.skip("Docker Compose CLI is required; no daemon is used")
    version = subprocess.run([executable, "compose", "version"], capture_output=True, timeout=10)
    if version.returncode:
        pytest.skip("Docker Compose plugin is unavailable")
    return executable


def render(docker, tmp_path, *, https=False, domain=None, bind="127.0.0.1"):
    envfile = tmp_path / "empty.env"
    envfile.write_text("")
    command = [docker, "compose", "--env-file", str(envfile), "-f", str(ROOT / "compose.yaml")]
    if https:
        command += ["-f", str(ROOT / "compose.https.yaml")]
    environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    environment.update(BIND_ADDRESS=bind, POSTGRES_PASSWORD="synthetic-compose-only")
    if domain is not None:
        environment["SPECHELPER_DOMAIN"] = domain
    return subprocess.run(
        command + ["config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_default_local_http_installation_is_compatible(docker, tmp_path):
    result = render(docker, tmp_path)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert "caddy" not in services
    assert services["frontend"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["frontend"]["ports"][0]["target"] == 3000


def test_https_requires_an_explicit_hostname(docker, tmp_path):
    result = render(docker, tmp_path, https=True)
    assert result.returncode != 0
    assert "SPECHELPER_DOMAIN" in result.stderr


@pytest.mark.parametrize(
    "domain,bind", [("localhost", "127.0.0.1"), ("spechelper.example.test", "0.0.0.0")]
)
def test_https_merges_one_origin_and_removes_direct_cleartext_exposure(
    docker, tmp_path, domain, bind
):
    result = render(docker, tmp_path, https=True, domain=domain, bind=bind)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for name in ("frontend", "backend", "worker", "database", "agent-runtime", "cli-maintenance"):
        assert not services[name].get("ports"), f"Unexpected public port on {name}"
    for name in ("backend", "worker"):
        environment = services[name]["environment"]
        assert environment["TRUSTED_ORIGINS"] == f"https://{domain}"
        assert environment["ALLOWED_HOSTS"].split(",")[0] == domain
        assert environment["SPECHELPER_REQUIRE_HTTPS"] == "1"
        assert environment["SPECHELPER_TRUST_PROXY"] == "1"
        assert environment["BIND_ADDRESS"] == bind
    caddy = services["caddy"]
    assert caddy["environment"]["SPECHELPER_DOMAIN"] == domain
    assert {(row["target"], row["protocol"]) for row in caddy["ports"]} == {
        (80, "tcp"),
        (443, "tcp"),
        (443, "udp"),
    }
    assert all(row["host_ip"] == bind for row in caddy["ports"])
    assert set(caddy["networks"]) == {"web-ingress"}
    assert caddy["read_only"]
    volumes = {row["target"]: row for row in caddy["volumes"]}
    assert volumes["/etc/caddy"]["read_only"]
    assert volumes["/data"]["type"] == "volume"
    assert volumes["/config"]["type"] == "volume"
