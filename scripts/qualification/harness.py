"""Frozen qualification packets and independent review, without model self-scoring."""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
UTC = timezone.utc
ROLES = {"analyst", "counter_analyst", "verifier"}
REQUIRED_TAGS = {
    "multi_repo", "conditional", "database_configuration", "history", "database_absent",
    "attachment", "rare_exception", "stale_sha", "scope_false_positive", "scope_false_negative",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Qualification JSON is unavailable, linked or oversized")
    return json.loads(path.read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def relative_file(root, relative):
    if not isinstance(relative, str) or PurePosixPath(relative).is_absolute() or "\\" in relative:
        raise ValueError("Qualification paths must be relative")
    if any(part in {"", ".", "..", ".git"} for part in relative.split("/")):
        raise ValueError("Qualification path is outside its packet")
    root = Path(root).resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root) or any(part.is_symlink() for part in (path, *path.parents) if part != root.parent):
        raise ValueError("Qualification file links are not allowed")
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Qualification fixture is missing or oversized")
    return path


def git(repository, *arguments, environment=None):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(Path(repository).resolve()),
         "-c", "core.hooksPath=" + os.devnull, "-C", str(repository), *arguments],
        env=environment, text=True, stderr=subprocess.PIPE,
    ).strip()


def source_files(root):
    root, result = Path(root), {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != ".git")
        for name in [*dirs, *names]:
            if name == ".git":
                continue
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Source snapshots cannot contain file or directory links")
            if path.is_file():
                digestor = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digestor.update(block)
                result[path.relative_to(root).as_posix()] = digestor.hexdigest()
    return result


def load_corpus(inputs=HERE):
    inputs = Path(inputs).resolve()
    corpus, expected = read_json(inputs / "corpus.json"), read_json(inputs / "expectations.json")
    cases = corpus.get("cases", [])
    ids = [case["id"] for case in cases]
    if not 20 <= len(cases) <= 30 or len(ids) != len(set(ids)) or set(ids) != set(expected["cases"]):
        raise ValueError("Qualification requires 20-30 distinct traced cases with separate expectations")
    if not {"development", "reserve"} <= {case["split"] for case in cases}:
        raise ValueError("A separate reserve portion is required")
    if not REQUIRED_TAGS <= {tag for case in cases for tag in case["tags"]}:
        raise ValueError("The required qualification situations are not covered")
    for case in cases:
        if not isinstance(case["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", case["id"]):
            raise ValueError("Case IDs must be plain identifiers, not filesystem paths")
        if case["workflow"] not in {"request", "question"} or case["language"] not in {"en", "fr"}:
            raise ValueError("Unknown case workflow or language")
        if case["kind"] not in {"analysis", "scope"} or case["database"] not in {"available", "absent"}:
            raise ValueError("Unknown case kind or database availability")
        if case["provenance"].get("origin") != "authored_synthetic":
            review = case["provenance"].get("privacy_review", {})
            if not case["provenance"].get("origin") or review.get("status") != "REVIEWED" or not all(
                isinstance(review.get(key), str) and review[key].strip()
                for key in ("reviewer", "method", "notes")
            ):
                raise ValueError("Non-synthetic provenance requires an explicit privacy review")
        for name in [*case["sources"], *case["attachments"]]:
            relative_file(inputs / "fixtures", name)
        row = expected["cases"][case["id"]]
        if not isinstance(row.get("human_review"), dict) or not row.get("observed_behavior") and case["kind"] != "scope":
            raise ValueError("Expected behavior and its human-review state are required")
        for fact in row["required_facts"]:
            for proof in fact["proof"]:
                text = relative_file(inputs / "fixtures", proof["repository"] + "/" + proof["path"]).read_text()
                excerpt = "\n".join(text.splitlines()[proof["start_line"] - 1:proof["end_line"]]).strip()
                if excerpt != proof["excerpt"].strip():
                    raise ValueError("Expected source provenance no longer matches the actual fixture")
    return corpus, expected


def validate_protocol(protocol):
    configs = protocol.get("configurations", [])
    if len(configs) < 2 or len({item["id"] for item in configs}) != len(configs):
        raise ValueError("At least two distinct configurations are required")
    distributions = []
    for config in configs:
        roles = config.get("roles", {})
        if set(roles) != ROLES:
            raise ValueError("Every configuration requires three independent public roles")
        for role in roles.values():
            if not all(role.get(key) for key in ("provider", "model", "family", "cli_version")):
                raise ValueError("Record exact model, family and CLI version for every role")
        distributions.append([(roles[role]["family"], roles[role].get("effort")) for role in sorted(ROLES)])
    if len({digest(value) for value in distributions}) < 2:
        raise ValueError("Configurations must differ in family distribution or explicit effort")
    if not protocol.get("instructions") or not protocol.get("tool_policy") or "skills" not in protocol:
        raise ValueError("Instructions, skills and tool policy must be frozen")
    return protocol


def prepare(destination, protocol, *, inputs=HERE):
    inputs = Path(inputs).resolve()
    corpus, expected = load_corpus(inputs)
    protocol = validate_protocol(protocol)
    fixtures = inputs / "fixtures"
    names = corpus.get("repository_directories")
    if names is None and inputs == HERE:
        names = ["contracts", "billing", "portal", "reporting"]
    if not isinstance(names, list) or not names:
        raise ValueError("Explicitly declare the authorized private repository directories")
    repositories = []
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name):
            raise ValueError("Repository identifiers must be plain directory names")
        source = fixtures / name
        if not source.is_dir() or source.is_symlink():
            raise ValueError("A declared source repository is unavailable or linked")
        source_files(source)
        commit = None
        if (source / ".git").exists():
            if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source.resolve() or git(source, "status", "--porcelain"):
                raise ValueError("Imported Git sources must be clean repository roots")
            commit = git(source, "rev-parse", "HEAD")
        repositories.append((name, source, commit))
    if not repositories or len(names) != len(set(names)):
        raise ValueError("Declare distinct authorized source repositories")
    if any(name.split("/", 1)[0] not in names for case in corpus["cases"] for name in case["sources"]):
        raise ValueError("Case source references must belong to declared repositories")
    available = any(case["database"] == "available" for case in corpus["cases"])
    period = corpus.get("database_observation_period", "2024-01-01/2025-12-31" if inputs == HERE else None)
    if available and (not isinstance(period, str) or not period.strip()):
        raise ValueError("Declare the private database observation period explicitly")
    database_files = {
        name: relative_file(fixtures / "database", name)
        for name in ("data.json", "schema.sql") if available or (fixtures / "database" / name).exists()
    }
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("The qualification destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1, "created_at": datetime.now(UTC).isoformat(),
        "corpus_sha256": digest(corpus), "expectations_sha256": digest(expected),
        "protocol_sha256": digest(protocol), "human_review": "PENDING", "cases": [],
    }
    date = "2026-01-01T00:00:00+00:00"
    environment = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    for case in corpus["cases"]:
        root = destination / "packets" / case["id"]
        root.mkdir(parents=True)
        packet = {
            "schema_version": 1, "case_id": case["id"], "workflow": case["workflow"],
            "language": case["language"], "kind": case["kind"], "need": case["need"],
            "environment": case["environment"], "protocol_sha256": digest(protocol),
            "repositories": [], "attachments": [],
            "database": {
                "state": case["database"],
                "snapshot_sha256": hashlib.sha256(database_files["data.json"].read_bytes()).hexdigest() if case["database"] == "available" else None,
                "schema_sha256": hashlib.sha256(database_files["schema.sql"].read_bytes()).hexdigest() if case["database"] == "available" else None,
                "observation_period": period if case["database"] == "available" else None,
            },
        }
        # Give independent reviewers the whole small authorized project, not an
        # evaluator-selected list of only those files that contain expected facts.
        if case["kind"] == "analysis":
            for name, source, commit in repositories:
                repository = root / "repositories" / name
                if commit:
                    repository.mkdir(parents=True)
                    git(repository, "init", "-q")
                    git(repository, "-c", "protocol.file.allow=always", "fetch", "-q", "--depth=1", "--no-tags", str(source), commit)
                    git(repository, "checkout", "-q", "--detach", "FETCH_HEAD")
                else:
                    shutil.copytree(source, repository)
                    git(repository, "init", "-q", "--initial-branch=main")
                    git(repository, "config", "user.name", "Qualification fixtures")
                    git(repository, "config", "user.email", "fixtures@example.invalid")
                    git(repository, "add", "--all")
                    git(repository, "commit", "-q", "-m", "test: freeze qualification sources", environment=environment)
                packet["repositories"].append({
                    "id": name, "path": "repositories/" + name,
                    "git_sha": git(repository, "rev-parse", "HEAD"), "files": source_files(repository),
                })
            for fact in expected["cases"][case["id"]]["required_facts"]:
                for proof in fact["proof"]:
                    text = relative_file(root / "repositories", proof["repository"] + "/" + proof["path"]).read_text()
                    excerpt = "\n".join(text.splitlines()[proof["start_line"]-1:proof["end_line"]]).strip()
                    if excerpt != proof["excerpt"].strip():
                        raise ValueError("Expected provenance differs from the captured Git sources")
        for index, name in enumerate(case["attachments"]):
            source = relative_file(fixtures, name)
            relative = "attachments/" + str(index + 1) + "-" + source.name
            target = root / relative
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            packet["attachments"].append({"path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        write_json(root / "packet.json", packet)
        manifest["cases"].append({"id": case["id"], "split": case["split"], "packet_sha256": digest(packet)})
    evaluator = destination / "evaluator"
    write_json(evaluator / "corpus.json", corpus)
    write_json(evaluator / "expectations.json", expected)
    for name, source in database_files.items():
        target = evaluator / "database" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
    write_json(destination / "protocol.json", protocol)
    write_json(destination / "manifest.json", manifest)
    return manifest


def check_study(study):
    study = Path(study).resolve()
    manifest, protocol = read_json(study / "manifest.json"), read_json(study / "protocol.json")
    corpus = read_json(study / "evaluator/corpus.json")
    expected = read_json(study / "evaluator/expectations.json")
    if digest(protocol) != manifest["protocol_sha256"] or digest(corpus) != manifest["corpus_sha256"] or digest(expected) != manifest["expectations_sha256"]:
        raise ValueError("The frozen qualification protocol, corpus or expected answers changed")
    for case in manifest["cases"]:
        root = study / "packets" / case["id"]
        packet = read_json(root / "packet.json")
        if digest(packet) != case["packet_sha256"]:
            raise ValueError("A qualification packet changed")
        if packet["database"]["state"] == "available":
            for name, key in (("data.json", "snapshot_sha256"), ("schema.sql", "schema_sha256")):
                actual = hashlib.sha256(relative_file(study / "evaluator/database", name).read_bytes()).hexdigest()
                if actual != packet["database"][key]:
                    raise ValueError("The frozen database fixture changed")
        for repository in packet["repositories"]:
            path = root / repository["path"]
            if git(path, "rev-parse", "HEAD") != repository["git_sha"] or source_files(path) != repository["files"] or git(path, "status", "--porcelain"):
                raise ValueError("Source SHA or content changed; repeat the qualification")
        for item in packet["attachments"]:
            path = relative_file(root, item["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("An attachment changed")
        authorized = {"packet.json"}
        for repository in packet["repositories"]:
            authorized.update(repository["path"] + "/" + name for name in repository["files"])
        authorized.update(item["path"] for item in packet["attachments"])
        actual = set(source_files(root))
        if actual != authorized:
            raise ValueError("Unexpected files could leak evaluator data into an agent packet")
    return manifest, protocol, corpus, expected


def export_review(study, destination):
    manifest, _, corpus, expected = check_study(study)
    lines = ["# Qualification corpus human review", "",
             ("These cases use authored synthetic business rules. No customer record or legal rule is asserted."
              if corpus.get("origin") == "authored_synthetic" else
              "This private corpus retains its declared provenance. Privacy review is separate from business and legal validation."),
             "A person familiar with the intended business use must validate the expected rules and representativeness.",
             "Review this document before viewing model results. Approval is bound to the frozen source and expected-answer hashes.",
             "", "Corpus: `" + manifest["corpus_sha256"] + "`", "",
             "Expected answers: `" + manifest["expectations_sha256"] + "`", ""]
    for case in corpus["cases"]:
        row = expected["cases"][case["id"]]
        lines.extend(["## " + case["id"] + " - " + case["title"], "",
                      "Workflow: " + case["workflow"] + ". Partition: " + case["split"] + ".", "",
                      case["need"], "", "Expected scope: `" + row["scope_status"] + "`.", ""])
        for fact in row["required_facts"]:
            lines.append("- " + fact["id"] + ": " + fact["statement"])
        if row["business_decisions"]:
            lines.extend(["", "Human business choices: " + "; ".join(row["business_decisions"])])
        packet_root = Path(study).resolve() / "packets" / case["id"]
        packet = read_json(packet_root / "packet.json")
        evidence = []
        for repository in packet["repositories"]:
            selected = [name for name in case["sources"] if name.startswith(repository["id"] + "/")]
            for name in selected:
                relative = name.split("/", 1)[1]
                target = packet_root / repository["path"] / relative
                evidence.append("[" + name + "](<" + str(target) + ">), Git `" + repository["git_sha"] + "`")
        lines.extend(["", "Evidence: " + ("; ".join(evidence) or "Deterministic scope decision; no project tools."), ""])
    lines.extend(["## Approval", "", "State the case IDs approved, reviewer identity and business familiarity. List corrections explicitly.",
                  "Approval confirms this corpus, not every future answer or repository. All cases remain PENDING until actual human review.", ""])
    Path(destination).write_text("\n".join(lines))
    return destination


def approve(study, *, reviewer, business_familiarity, attestation, case_ids):
    manifest, _, corpus, _ = check_study(study)
    if not all(isinstance(value, str) and value.strip() for value in (reviewer, business_familiarity, attestation)):
        raise ValueError("Actual human reviewer, business familiarity and attestation are required")
    selected = sorted(set(case_ids))
    if not selected or not set(selected) <= {case["id"] for case in corpus["cases"]}:
        raise ValueError("Specify the cases actually reviewed")
    receipt = {
        "schema_version": 1, "reviewer": reviewer.strip(), "method": "human_business_review",
        "business_familiarity": business_familiarity.strip(), "attestation": attestation.strip(),
        "case_ids": selected, "corpus_sha256": manifest["corpus_sha256"],
        "expectations_sha256": manifest["expectations_sha256"],
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
    write_json(Path(study) / "evaluator/human-review.json", receipt)
    return receipt


def human_reviewed(study, manifest, case_id):
    path = Path(study) / "evaluator/human-review.json"
    if not path.exists():
        return False
    receipt = read_json(path)
    return (
        receipt.get("method") == "human_business_review" and bool(receipt.get("reviewer"))
        and bool(receipt.get("business_familiarity")) and bool(receipt.get("attestation"))
        and receipt.get("corpus_sha256") == manifest["corpus_sha256"]
        and receipt.get("expectations_sha256") == manifest["expectations_sha256"]
        and case_id in receipt.get("case_ids", [])
    )


def measured_number(value, *, integer=False):
    return isinstance(value, int if integer else (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def measured_usage(attempts):
    """Separate complete totals from measured subtotals when a provider omits usage."""
    totals, coverage = {}, {}
    for metric in ("input_tokens", "output_tokens", "total_tokens"):
        values = [
            attempt["usage"].get(metric) if isinstance(attempt.get("usage"), dict) else None
            for attempt in attempts
        ]
        known = [value for value in values if measured_number(value, integer=True)]
        totals[metric] = sum(known) if values and len(known) == len(values) else None
        coverage[metric] = {
            "observed_attempts": len(known), "unknown_attempts": len(values) - len(known),
            "observed_tokens": sum(known) if known else None,
        }
    return totals, coverage


def compare(study, runs, reviews):
    manifest, protocol, corpus, expected = check_study(study)
    configs = {row["id"]: row for row in protocol["configurations"]}
    by_case = {row["id"]: row for row in manifest["cases"]}
    case_definitions = {row["id"]: row for row in corpus["cases"]}
    if len(runs) < 2 or len({run["configuration_id"] for run in runs}) != len(runs):
        raise ValueError("Supply at least two distinct configuration runs")
    summaries = []
    for run in runs:
        config_id = run["configuration_id"]
        if config_id not in configs or run["manifest_sha256"] != digest(manifest):
            raise ValueError("Runs must use the identical frozen source/data/protocol manifest")
        supplied = {row["case_id"]: row for row in run.get("cases", [])}
        if len(supplied) != len(run.get("cases", [])) or not set(supplied) <= set(by_case):
            raise ValueError("Duplicate or unknown case observations")
        rows = []
        all_attempts = []
        contexts = set()
        for case_id, frozen in by_case.items():
            row = supplied.get(case_id)
            baseline = expected["cases"][case_id]
            summary = {"case_id": case_id, "split": frozen["split"], "human_expected_review": human_reviewed(study, manifest, case_id),
                       "kind": case_definitions[case_id]["kind"],
                       "status": row.get("status", "NOT_RUN") if row else "NOT_RUN", "semantic_review": "UNREVIEWED",
                       "material_errors": None, "decisive_omissions": None, "unsupported_claims": None,
                       "expected_facts": len(baseline["required_facts"]), "covered_facts": None,
                       "false_positive": None, "false_negative": None, "clarification_relevance": None}
            if row:
                if row["packet_sha256"] != frozen["packet_sha256"]:
                    raise ValueError("A run uses another case packet")
                attempts = row.get("attempts", [])
                successful = {item["role"] for item in attempts if item.get("status") == "SUCCESS"}
                if case_definitions[case_id]["kind"] == "analysis" and summary["status"] == "COMPLETE" and successful != ROLES:
                    raise ValueError("A complete analysis requires all three successful independent roles")
                if case_definitions[case_id]["kind"] == "scope" and attempts:
                    raise ValueError("Deterministic scope cases must not invoke the analysis pipeline")
                for attempt in attempts:
                    context = attempt.get("context_id")
                    if not context or context in contexts:
                        raise ValueError("Role contexts must be independent across cases and attempts")
                    contexts.add(context)
                    if attempt.get("role") not in ROLES:
                        raise ValueError("Unknown public role")
                    expected_role = configs[config_id]["roles"][attempt["role"]]
                    if any(attempt.get(key) != expected_role.get(key) for key in (
                        "provider", "model", "family", "cli_version", "effort",
                    )):
                        raise ValueError("Observed role identity must match the frozen model, effort and CLI version")
                    all_attempts.append(attempt)
                if case_definitions[case_id]["kind"] == "scope" and attempts:
                    raise ValueError("Deterministic scope cases must not invoke the analysis pipeline")
                actual = row.get("scope_status")
                if actual in {"IN_SCOPE", "OUT_OF_SCOPE", "NEEDS_CLARIFICATION"}:
                    summary["false_positive"] = int(actual != "IN_SCOPE" and baseline["scope_status"] == "IN_SCOPE")
                    summary["false_negative"] = int(actual == "IN_SCOPE" and baseline["scope_status"] != "IN_SCOPE")
                    summary["scope_expected"] = baseline["scope_status"]
                    summary["scope_actual"] = actual
                independent = [review for review in reviews if review.get("configuration_id") == config_id and review.get("case_id") == case_id]
                if len(independent) > 1:
                    raise ValueError("Conflicting independent reviews")
                if independent:
                    review = independent[0]
                    required = {fact["id"] for fact in baseline["required_facts"]}
                    facts = review.get("facts", [])
                    if (
                        review.get("packet_sha256") != frozen["packet_sha256"]
                        or review.get("output_sha256") != digest(row.get("output"))
                        or not review.get("reviewer")
                        or review.get("method") not in {"human_source_review", "independent_source_audit"}
                        or {fact.get("id") for fact in facts} != required or len(facts) != len(required)
                        or review.get("all_material_claims_reviewed") is not True
                    ):
                        raise ValueError("Independent review must cover all expected facts and the exact final output")
                    for fact in facts:
                        if not all(isinstance(fact.get(key), bool) for key in ("present", "correct", "evidence_valid")):
                            raise ValueError("Review factual assertions explicitly; do not infer quality from keywords")
                    summary.update(
                        semantic_review="REVIEWED", covered_facts=sum(f["present"] and f["correct"] and f["evidence_valid"] for f in facts),
                        decisive_omissions=sum(not f["present"] for f in facts),
                        material_errors=len(review.get("material_errors", [])),
                        unsupported_claims=len(review.get("unsupported_claims", [])),
                        clarification_relevance=review.get("clarification_relevance", "UNREVIEWED"),
                    )
                if not measured_number(row.get("elapsed_seconds")):
                    raise ValueError("Case duration must be observed")
                summary["elapsed_seconds"] = row["elapsed_seconds"]
                summary["execution_seconds"] = row.get("execution_seconds")
            rows.append(summary)
        totals, usage_coverage = measured_usage(all_attempts)
        elapsed = [row.get("elapsed_seconds") for row in rows]
        execution = [row.get("execution_seconds") for row in rows if case_definitions[row["case_id"]]["kind"] == "analysis"]
        splits = {}
        for split in ("development", "reserve"):
            subset = [row for row in rows if row["split"] == split]
            splits[split] = {
                "cases": len(subset),
                "measured_cases": sum(row["status"] in {"COMPLETE", "PARTIAL"} for row in subset),
                "reviewed_cases": sum(row["semantic_review"] == "REVIEWED" for row in subset),
                "material_errors": sum(row["material_errors"] for row in subset) if all(row["material_errors"] is not None for row in subset) else None,
                "decisive_omissions": sum(row["decisive_omissions"] for row in subset) if all(row["decisive_omissions"] is not None for row in subset) else None,
                "elapsed_seconds": sum(row["elapsed_seconds"] for row in subset) if all(measured_number(row.get("elapsed_seconds")) for row in subset) else None,
                "scope_false_positives": sum(row["false_positive"] for row in subset if row["false_positive"] is not None),
                "scope_false_negatives": sum(row["false_negative"] for row in subset if row["false_negative"] is not None),
                "scope_measured_cases": sum(row["false_positive"] is not None for row in subset),
            }
        summaries.append({
            "configuration_id": config_id, "cases": rows, "usage": totals,
            "usage_coverage": usage_coverage,
            "splits": splits,
            "elapsed_seconds": sum(elapsed) if all(measured_number(value) for value in elapsed) else None,
            "execution_seconds": sum(execution) if execution and all(measured_number(value) for value in execution) else None,
            "monetary_cost": None,
            "reviewed_cases": sum(row["semantic_review"] == "REVIEWED" for row in rows),
            "human_approved_cases": sum(row["human_expected_review"] for row in rows),
            "material_errors": sum(row["material_errors"] for row in rows) if all(row["material_errors"] is not None for row in rows) else None,
            "decisive_omissions": sum(row["decisive_omissions"] for row in rows) if all(row["decisive_omissions"] is not None for row in rows) else None,
            "measurement_complete": all(row["status"] in {"COMPLETE", "PARTIAL"} for row in rows),
        })
    return {
        "schema_version": 1, "manifest_sha256": digest(manifest), "configurations": summaries,
        "qualification_status": "REVIEWED_WITH_LIMITS" if all(
            item["measurement_complete"] and item["reviewed_cases"] == len(by_case) and item["human_approved_cases"] == len(by_case)
            for item in summaries
        ) else "NOT_QUALIFIED",
        "limits": [("Authored synthetic corpus; representativeness requires human review"
                    if corpus.get("origin") == "authored_synthetic" else
                    "Private corpus with declared provenance; representativeness requires human review"),
                   "No universal confidence score or certification", "Monetary cost is unknown without actual billing observations", "Finite database observations apply only to the frozen population and period"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validation = sub.add_parser("validate")
    validation.add_argument("--inputs", type=Path, default=HERE)
    prepare_args = sub.add_parser("prepare")
    prepare_args.add_argument("study", type=Path)
    prepare_args.add_argument("--protocol", type=Path, required=True)
    prepare_args.add_argument("--inputs", type=Path, default=HERE)
    check = sub.add_parser("check")
    check.add_argument("study", type=Path)
    review = sub.add_parser("review-document")
    review.add_argument("study", type=Path)
    review.add_argument("--output", type=Path, required=True)
    approval = sub.add_parser("record-human-review")
    approval.add_argument("study", type=Path)
    for name in ("reviewer", "business-familiarity", "attestation"):
        approval.add_argument("--" + name, required=True)
    approval.add_argument("--cases", nargs="+", required=True)
    comparison = sub.add_parser("compare")
    comparison.add_argument("study", type=Path)
    comparison.add_argument("--runs", type=Path, nargs="+", required=True)
    comparison.add_argument("--reviews", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        corpus, _ = load_corpus(args.inputs)
        print(json.dumps({"cases": len(corpus["cases"]), "human_validation": corpus["human_validation"]}))
    elif args.command == "prepare":
        manifest = prepare(args.study, read_json(args.protocol), inputs=args.inputs)
        print(json.dumps({"cases": len(manifest["cases"]), "manifest_sha256": digest(manifest)}))
    elif args.command == "check":
        manifest, _, _, _ = check_study(args.study)
        print(json.dumps({"cases": len(manifest["cases"]), "frozen_inputs_valid": True}))
    elif args.command == "review-document":
        export_review(args.study, args.output)
        print(json.dumps({"review_document": str(args.output), "human_approval": "PENDING"}))
    elif args.command == "record-human-review":
        receipt = approve(args.study, reviewer=args.reviewer, business_familiarity=args.business_familiarity, attestation=args.attestation, case_ids=args.cases)
        print(json.dumps({"reviewed_cases": len(receipt["case_ids"])}))
    else:
        result = compare(args.study, [read_json(path) for path in args.runs], read_json(args.reviews))
        write_json(args.output, result)
        print(json.dumps({"qualification_status": result["qualification_status"]}))


if __name__ == "__main__":
    main()
