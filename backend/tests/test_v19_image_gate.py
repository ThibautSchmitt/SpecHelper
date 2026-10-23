"""A review cannot hide a new/fixable vulnerability or replace exact-image evidence."""

import json
from datetime import date, timedelta

import pytest
from scripts.security.check_image_report import check


@pytest.fixture
def evidence(tmp_path):
    purl = "pkg:deb/debian/fixture@1.0?arch=amd64&distro=debian-13.7"
    values = {
        "trivy-image.json": {
            "Metadata": {"ImageID": "sha256:fixture", "OS": {"Family": "debian"}},
            "Results": [{"Type": "debian", "Vulnerabilities": [{"VulnerabilityID": "CVE-fixture", "PkgName": "fixture", "Severity": "HIGH", "PkgIdentifier": {"PURL": purl}}]}],
        },
        "image-evidence.json": {
            "image_id": "sha256:fixture", "component": "backend",
            "checks": {"nonroot": True, "no_suid_sgid": True, "no_new_privileges": True, "no_fstab_mounts": True, "unused_component_absent": True},
        },
        "policy.json": {"reviews": [{
            "cve": "CVE-fixture", "reason": "Affected component is absent", "source": "https://example.invalid/advisory",
            "owner": "Fixture reviewer", "reviewed": date.today().isoformat(), "expires": (date.today() + timedelta(days=1)).isoformat(),
            "required_checks": ["unused_component_absent"], "packages": [{"purl": purl, "components": ["backend"]}],
        }]},
    }
    def save():
        for name, value in values.items():
            (tmp_path / name).write_text(json.dumps(value))
    save()
    return tmp_path, values, save


def test_review_preserves_finding_count_and_requires_material_image_evidence(evidence):
    directory, _, _ = evidence
    check(directory, "backend", directory / "policy.json")
    result = json.loads((directory / "image-review.json").read_text())
    assert result["high_critical_findings"] == result["reviewed_with_conditions"] == 1
    assert result["raw_report_preserved"]
    assert (directory / "trivy-image.json").is_file()


@pytest.mark.parametrize("mutation", ["fix", "new_package", "new_cve", "application", "secret", "wrong_image", "missing_control", "expired", "long_expiry"])
def test_gate_rejects_unreviewed_changes_and_missing_evidence(evidence, mutation):
    directory, values, save = evidence
    finding = values["trivy-image.json"]["Results"][0]["Vulnerabilities"][0]
    review = values["policy.json"]["reviews"][0]
    if mutation == "fix":
        finding["FixedVersion"] = "1.1"
    elif mutation == "new_package":
        finding["PkgIdentifier"]["PURL"] += "-changed"
    elif mutation == "new_cve":
        finding["VulnerabilityID"] = "CVE-unreviewed"
    elif mutation == "application":
        values["trivy-image.json"]["Results"][0]["Type"] = "node-pkg"
    elif mutation == "secret":
        values["trivy-image.json"]["Results"][0]["Secrets"] = [{"synthetic": True}]
    elif mutation == "wrong_image":
        values["image-evidence.json"]["image_id"] = "sha256:other"
    elif mutation == "missing_control":
        values["image-evidence.json"]["checks"].pop("unused_component_absent")
    elif mutation == "expired":
        review["reviewed"] = (date.today() - timedelta(days=2)).isoformat()
        review["expires"] = (date.today() - timedelta(days=1)).isoformat()
    elif mutation == "long_expiry":
        review["expires"] = (date.today() + timedelta(days=365)).isoformat()
    save()
    with pytest.raises(ValueError):
        check(directory, "backend", directory / "policy.json")
