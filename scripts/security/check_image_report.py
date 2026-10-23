"""Keep raw findings and require exact, expiring applicability reviews and image evidence."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path


def read(path):
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError("Missing image security evidence: " + path.name)
    return json.loads(path.read_text())


def check(directory, component, policy_path):
    report = read(directory / "trivy-image.json")
    evidence = read(directory / "image-evidence.json")
    policy = read(policy_path)
    image_id = report.get("Metadata", {}).get("ImageID")
    if not image_id or evidence.get("image_id") != image_id or evidence.get("component") != component:
        raise ValueError("Scanner and probe must identify the same exact image")
    if not report.get("Results") or not report.get("Metadata", {}).get("OS", {}).get("Family"):
        raise ValueError("Image scan lacks operating-system coverage")
    checks = evidence.get("checks", {})
    required = {"no_suid_sgid", "no_new_privileges", "no_fstab_mounts"}
    if component in {"backend", "frontend"}:
        required.add("nonroot")
    if any(checks.get(name) is not True for name in required):
        raise ValueError("Image privilege checks failed or are missing")
    if component == "runtime":
        path = directory / "runtime-boundaries.jsonl"
        if not path.is_file() or path.is_symlink():
            raise ValueError("Runtime boundary evidence is missing")
        boundaries = {}
        for line in path.read_text().splitlines():
            boundaries.update(json.loads(line))
        if boundaries.get("uid") != 10001 or any(boundaries.get(name) is not True for name in (
            "capabilities_zero", "source_writes_denied", "cross_session_hidden",
            "arbitrary_network_denied", "provider_only", "credentials_hidden",
            "seccomp_enforced", "forbidden_operations_denied_per_carrier", "pdf_parser_confined",
        )):
            raise ValueError("Runtime boundary probes failed or lack required coverage")
        if set(boundaries.get("indirect_injection_carriers", [])) != {"README", "PDF", "ticket", "database"}:
            raise ValueError("Runtime injection-carrier coverage is incomplete")
    reviews = policy.get("reviews", [])
    for review in reviews:
        if not all(review.get(name) for name in ("cve", "reason", "source", "owner", "reviewed", "expires", "packages", "required_checks")):
            raise ValueError("Incomplete image applicability review")
        reviewed_on = date.fromisoformat(review["reviewed"])
        expires = date.fromisoformat(review["expires"])
        if reviewed_on > date.today() or not reviewed_on < expires <= reviewed_on + timedelta(days=31):
            raise ValueError("Image applicability reviews must expire within 31 days")
        if expires < date.today():
            raise ValueError("Image applicability review expired: " + review["cve"])
    blocking, reviewed, total = [], [], 0
    for result in report["Results"]:
        if result.get("Secrets"):
            raise ValueError("Image secret findings require correction")
        for finding in result.get("Vulnerabilities", []):
            if finding.get("Severity") not in {"HIGH", "CRITICAL"}:
                continue
            total += 1
            purl = finding.get("PkgIdentifier", {}).get("PURL")
            matching = [review for review in reviews if
                review["cve"] == finding.get("VulnerabilityID")
                and result.get("Type") == "debian"
                and not finding.get("FixedVersion")
                and any(item.get("purl") == purl and component in item.get("components", []) for item in review["packages"])
                and all(checks.get(name) is True for name in review["required_checks"])
            ]
            label = finding.get("VulnerabilityID", "unknown") + ":" + finding.get("PkgName", "unknown")
            (reviewed if matching else blocking).append(label)
    if blocking:
        raise ValueError("Unreviewed or fixable high/critical findings: " + ", ".join(blocking))
    summary = {"component": component, "image_id": image_id, "high_critical_findings": total,
               "reviewed_with_conditions": len(reviewed), "unreviewed_findings": 0,
               "raw_report_preserved": True}
    (directory / "image-review.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise SystemExit(str(exc)) from None
