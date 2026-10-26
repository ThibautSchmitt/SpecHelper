"""Bounded claim reports checked against frozen Git sources and actual SQL receipts."""

import copy
import re
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .web_evidence import WebReceipt, WebSource, actual_web_receipts, check_web_source

Text = Annotated[str, Field(min_length=1, max_length=4000)]


class StrictEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimScope(StrictEvidence):
    environment: str = Field(
        default="", max_length=200,
        description="Copy the exact frozen environment name from the supplied context; do not replace it with a descriptive label.",
    )
    conditions: list[Text] = Field(default_factory=list, max_length=12)
    period: str = Field(default="", max_length=1000)
    population: str = Field(default="", max_length=1000)
    sample_limits: str = Field(default="", max_length=2000)


class GitSource(StrictEvidence):
    kind: Literal["git"]
    repository: str = Field(
        min_length=1, max_length=255,
        description="Exact repository identifier from the frozen baseline, including its owner when present.",
    )
    commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    path: str = Field(
        min_length=1, max_length=1000,
        description="Path relative to this repository's root. Do not include /workspace or repeat the repository identifier. For repository org/repo, a file at its root is path policy.py, not org/repo/policy.py.",
    )
    symbol: str = Field(default="", max_length=500)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=6000)

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        if (
            PurePosixPath(value).is_absolute()
            or "\\" in value
            or any(part in {"", ".", "..", ".git"} for part in value.split("/"))
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("Evidence uses normalized repository-relative paths")
        return value

    @model_validator(mode="after")
    def bounded_excerpt(self):
        if self.line_end < self.line_start or self.line_end - self.line_start >= 100:
            raise ValueError("An evidence excerpt spans at most 100 source lines")
        return self


class SQLSource(StrictEvidence):
    kind: Literal["sql"]
    query_id: str = Field(min_length=1, max_length=100)


class SQLReceipt(StrictEvidence):
    query_id: str = Field(min_length=1, max_length=100)
    sql: str = Field(default="", max_length=20000)
    checked_at: str = Field(min_length=1, max_length=50)
    status: Literal["checked", "unavailable", "rejected"]
    row_count: int = Field(default=0, ge=0, le=201)
    truncated: bool = False
    rows_exposed: int = Field(default=0, ge=0, le=200)

    @field_validator("checked_at")
    @classmethod
    def aware_timestamp(cls, value):
        if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("A SQL observation needs a timezone-aware timestamp")
        return value


class Counterexample(StrictEvidence):
    description: Text
    interpretation: Literal["current_behavior", "historical_anomaly", "unknown"]


class EvidenceClaim(StrictEvidence):
    id: str = Field(min_length=1, max_length=100)
    statement: Text
    kind: Literal["observed", "interpretation", "contradiction", "unknown"]
    status: Literal["supported", "partial", "contradicted", "unverified"]
    basis: Literal["deployment", "official_rule", "external_contract"] = "deployment"
    scope: ClaimScope
    sources: list[Annotated[GitSource | SQLSource | WebSource, Field(discriminator="kind")]] = (
        Field(default_factory=list, max_length=20)
    )
    counterexamples: list[Counterexample] = Field(default_factory=list, max_length=12)
    verification_notes: str = Field(default="", max_length=4000)
    universal: bool = False
    material: bool = True


class DatabaseEvidence(StrictEvidence):
    status: Literal["not_configured", "checked", "unavailable", "not_checked"] = "not_checked"
    scope: str = Field(default="", max_length=2000)
    limitations: list[Text] = Field(default_factory=list, max_length=20)
    checks: list[SQLReceipt] = Field(default_factory=list, max_length=100)


def public_report(report, language="en"):
    """Retain verification limits while removing runtime paths from narrative prose.

    Source excerpts, SQL receipts and Web receipts remain exact provenance. They
    are not rewritten to make an otherwise invalid citation appear valid.
    """
    from .question_outputs import PRIVATE_PATH

    path = re.compile("(?:" + PRIVATE_PATH.pattern + r")[^\s\"'`<>\[\](){},;]*")

    def clean(value):
        if isinstance(value, str):
            marker = "[chemin privé]" if language == "fr" else "[private runtime path]"
            return path.sub(marker, value)
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            return {
                key: item if key in {"sources", "checks", "web_references"} else clean(item)
                for key, item in value.items()
            }
        return value

    return ReliabilityReport.model_validate(clean(report.model_dump()))


class ReliabilityReport(StrictEvidence):
    claims: list[EvidenceClaim] = Field(default_factory=list, max_length=30)
    database: DatabaseEvidence = Field(default_factory=DatabaseEvidence)
    limitations: list[Text] = Field(default_factory=list, max_length=30)
    blocking: bool = False
    web_references: list[WebReceipt] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def distinct_claims(self):
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError("Claim identifiers must be distinct")
        return self


def checked_git_source(source, baseline, workspace):
    """Verify exact provenance and excerpt; matching text does not prove its interpretation."""
    row = next((item for item in baseline if item["repository"] == source.repository), None)
    if row is None or row["sha"] != source.commit:
        return False
    root = Path(workspace).resolve()
    repository = root / source.repository
    path = repository / source.path
    try:
        if (
            not repository.resolve().is_relative_to(root)
            or not path.resolve().is_relative_to(repository.resolve())
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 4 * 1024 * 1024
        ):
            return False
        lines = path.read_text(encoding="utf-8").splitlines()
        from .git import run as git_run

        object_name = source.commit + ":" + source.path
        original = git_run("-C", repository, "rev-parse", "--verify", object_name, timeout=5)
        actual_blob = git_run(
            "-C", repository, "hash-object", "--no-filters", "--", source.path, timeout=5
        )
        if original != actual_blob:
            return False
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        return False
    if source.line_end > len(lines):
        return False
    actual = "\n".join(lines[source.line_start - 1 : source.line_end]).strip()
    return bool(actual) and source.excerpt.strip() == actual


def actual_receipts(run):
    """Only service-returned observations may establish that a database was queried."""
    receipts = []
    for raw in run.orchestration.get("database_checks", [])[:100]:
        try:
            receipt = SQLReceipt.model_validate(raw)
        except ValueError:
            continue
        if receipt.query_id not in {item.query_id for item in receipts}:
            receipts.append(receipt)
    return receipts


def check_report(report, request, run, workspace):
    """Qualify claims, never bypass independent review or turn a sample into certainty."""
    from .sensitive_data import configured_secrets, redact

    raw = report.model_dump() if isinstance(report, ReliabilityReport) else report
    value = ReliabilityReport.model_validate(redact(copy.deepcopy(raw), configured_secrets()))
    receipts = actual_receipts(run)
    web_receipts = actual_web_receipts(run)
    # Page observations come exclusively from the runtime; ignore model-authored copies.
    cited_web_ids = {
        source.reference_id
        for claim in value.claims
        for source in claim.sources
        if isinstance(source, WebSource)
    }
    value.web_references = [
        receipt for receipt in web_receipts if receipt.reference_id in cited_web_ids
    ]
    successful = {item.query_id: item for item in receipts if item.status == "checked"}
    has_database = bool(request.database_snapshot)
    value.database.checks = receipts
    value.database.status = (
        "not_configured"
        if not has_database
        else "checked"
        if successful
        else "unavailable"
        if any(item.status == "unavailable" for item in receipts)
        else "not_checked"
    )
    if not has_database:
        value.database.scope = ""
        value.database.limitations = [
            "No business database is configured. Real records were not checked."
        ]
    elif not successful:
        value.database.limitations = [
            *value.database.limitations[:19],
            "No successful authorized database query was observed. Real data conclusions remain unverified.",
        ]
    else:
        value.database.limitations = list(
            dict.fromkeys(
                [
                    *value.database.limitations[:18],
                    "Database observations apply only to the queried population and time.",
                    "No counterexample found does not establish universal validity.",
                ]
            )
        )
    if not value.claims:
        value.blocking = True
        value.limitations = [
            *value.limitations[:29],
            "The analysis contains no explicit verified claims.",
        ]
    baseline = run.context_snapshot.get("dossier", {}).get("baseline") or request.baseline
    expected_environment = request.environment_name_snapshot or (
        request.environment.name if request.environment_id else ""
    )
    for claim in value.claims:
        verified_sources, problems = [], []
        for source in claim.sources:
            if isinstance(source, GitSource):
                verified = checked_git_source(source, baseline, workspace)
            elif isinstance(source, SQLSource):
                verified = has_database and source.query_id in successful
            else:
                verified, web_problems = check_web_source(source, web_receipts)
                if claim.basis == "official_rule" and not source.effective_date:
                    web_problems.append(
                        "An external rule without a stated effective date does not establish a current obligation."
                    )
                problems.extend(web_problems)
                if web_problems and claim.status == "supported":
                    claim.status = "partial"
            if verified:
                verified_sources.append(source)
            else:
                problems.append(
                    "A cited source could not be matched to the frozen code or an actual authorized query."
                )
        claim.sources = verified_sources
        if (
            claim.basis == "deployment"
            and verified_sources
            and all(isinstance(source, WebSource) for source in verified_sources)
        ):
            problems.append(
                "External documentation does not establish this deployment's observed behavior."
            )
            if claim.status == "supported":
                claim.status = "partial"
        if (
            claim.scope.environment
            and expected_environment
            and claim.scope.environment != expected_environment
        ):
            problems.append("The claimed environment does not match this analysis.")
            if claim.status == "supported":
                claim.status = "partial"
        claim.scope.environment = expected_environment
        if not verified_sources:
            claim.status = "unverified"
            problems.append("No inspected source supports this claim.")
        if (
            not claim.scope.conditions
            or any(not item.strip() for item in claim.scope.conditions)
            or not claim.scope.population.strip()
            or not claim.scope.sample_limits.strip()
        ):
            problems.append("The conditions, population or observation limits are incomplete.")
            if claim.status == "supported":
                claim.status = "partial"
        if not claim.scope.period.strip():
            problems.append("The observation period is missing.")
            if claim.status == "supported":
                claim.status = "partial"
        claim.universal = claim.universal or bool(
            re.search(
                r"(?i)\b(?:without exception|in every case|always possible|never fails|in all cases|sans exception|dans tous les cas|toujours possible|aucune exception)\b",
                claim.statement,
            )
        )
        if claim.universal:
            problems.append(
                "A finite inspection cannot certify this universal statement; state the verified conditions and exceptions."
            )
            if claim.status == "supported":
                claim.status = "partial"
        if claim.counterexamples and claim.universal:
            claim.status = "contradicted"
        if any(item.interpretation == "historical_anomaly" for item in claim.counterexamples):
            problems.append(
                "A historical anomaly does not establish that the current application permits that behavior."
            )
            if claim.status == "supported":
                claim.status = "partial"
        if claim.kind == "unknown" and claim.status == "supported":
            claim.status = "unverified"
        if claim.kind == "contradiction" and claim.status == "supported":
            claim.status = "contradicted"
        if re.search(
            r"(?i)(?:100\s*%|\b(?:certified|certainty|confidence|certifie|certitude|confiance)\b.{0,15}\d+\s*%)",
            claim.statement,
        ):
            claim.status = "unverified"
            problems.append("Numerical certification is not supported by these observations.")
        claim.verification_notes = "\n".join(
            dict.fromkeys([claim.verification_notes, *problems])
        ).strip()[:4000]
        if claim.material and claim.status in {"partial", "contradicted", "unverified"}:
            value.blocking = True
    return value
