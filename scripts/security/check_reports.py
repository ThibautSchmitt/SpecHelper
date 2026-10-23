"""Fail closed on absent, malformed or empty-coverage source security reports."""

import json
import sys
from datetime import date
from pathlib import Path


def read(directory, name):
    path = directory / name
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError(f"Missing scanner report: {name}")
    return json.loads(path.read_text())


def check(directory, exception_path):
    leaks = read(directory, "gitleaks.json")
    if not isinstance(leaks, list) or leaks:
        raise ValueError("Secret scan requires review")
    sast = read(directory, "semgrep.json")
    if not sast.get("paths", {}).get("scanned") or sast.get("errors") or sast.get("results"):
        raise ValueError("SAST failed, found issues or did not scan source")
    python = read(directory, "pip-audit.json")
    if not python.get("dependencies") or any(item.get("vulns") for item in python["dependencies"]):
        raise ValueError("Python audit failed or found vulnerabilities")
    if any(item.get("skip_reason") for item in python["dependencies"]):
        raise ValueError("Python dependencies were skipped by the audit")
    npm = read(directory, "npm-audit.json")
    if npm.get("error") or not npm.get("metadata", {}).get("dependencies", {}).get("total"):
        raise ValueError("npm audit failed or did not inspect dependencies")
    if npm.get("metadata", {}).get("vulnerabilities", {}).get("total") != 0:
        raise ValueError("npm audit found vulnerabilities")
    infrastructure = read(directory, "trivy-iac.json")
    if not infrastructure.get("Results"):
        raise ValueError("Infrastructure scan did not inspect configuration")
    exceptions = json.loads(exception_path.read_text())["exceptions"]
    for exception in exceptions:
        if date.fromisoformat(exception["expires"]) < date.today():
            raise ValueError("Infrastructure exception expired: " + exception["id"])
        if not all(exception.get(field) for field in ("id", "scanner_id", "target", "owner", "reason", "required_evidence")):
            raise ValueError("Incomplete infrastructure exception")
        if any(character in exception["target"] for character in "*?[]"):
            raise ValueError("Infrastructure exceptions must name one exact source file")
    blocking = []
    for result in infrastructure["Results"]:
        for finding in result.get("Misconfigurations", []):
            accepted = [exception for exception in exceptions if exception["scanner_id"] == finding["ID"] and exception["target"] == result["Target"]]
            if not accepted:
                blocking.append(result["Target"] + ":" + finding["ID"])
    if blocking:
        raise ValueError("Infrastructure scan found blocking misconfiguration: " + ", ".join(blocking))
    print("Source scanner reports cover code, dependencies and infrastructure with no unreviewed blocking findings")


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else Path("security/trivy-exceptions.json"))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise SystemExit(str(exc)) from None
