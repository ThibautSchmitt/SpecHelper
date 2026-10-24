"""Measure optional navigation honestly against fixed synthetic Git snapshots.

The runner never launches inference implicitly. Native model responses and usage
can be imported after an explicitly authorized isolated analysis comparison.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus.json"
MODES = {"source", "codebase-memory-mcp"}


def command(arguments, *, cwd=None, environment=None):
    return subprocess.check_output(
        ["rtk", "proxy", *arguments], cwd=cwd, env=environment, text=True
    ).strip()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def cases():
    return json.loads(CORPUS.read_text())["cases"]


def manifest_for(repository):
    return {
        path.relative_to(repository).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(repository.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repository).parts
    }


def prepare(destination):
    """Create disposable fixtures; refuse to overwrite an existing directory."""
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("The study destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "kind": "synthetic-fixed-sha", "cases": []}
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    }
    for case in cases():
        repository = destination / "repos" / case["id"]
        shutil.copytree(HERE / "corpus" / case["id"], repository)
        command(["git", "init", "-q", "--initial-branch=main"], cwd=repository)
        command(["git", "config", "user.name", "Synthetic evaluation"], cwd=repository)
        command(["git", "config", "user.email", "fixture@example.invalid"], cwd=repository)
        command(["git", "add", "--all"], cwd=repository)
        command(
            ["git", "commit", "-q", "-m", "test: pin synthetic evaluation corpus"],
            cwd=repository,
            environment=environment,
        )
        manifest["cases"].append(
            {
                "id": case["id"],
                "git_sha": command(["git", "rev-parse", "HEAD"], cwd=repository),
                "files": manifest_for(repository),
            }
        )
    write_json(destination / "manifest.json", manifest)
    return manifest


def check_snapshot(repository, expected, index=None):
    """An index hit is unusable if the actual repository or index snapshot drifts."""
    repository = Path(repository)
    actual = command(["git", "rev-parse", "HEAD"], cwd=repository)
    if actual != expected["git_sha"] or manifest_for(repository) != expected["files"]:
        raise ValueError("The source snapshot changed; re-index and repeat the study")
    if command(["git", "status", "--porcelain"], cwd=repository):
        raise ValueError("The evaluation source snapshot must be clean")
    if index is not None and (
        index.get("git_sha") != actual
        or index.get("case_id") != expected["id"]
        or index.get("files") != expected["files"]
    ):
        raise ValueError("The optional index does not match this authorized repository snapshot")


def source_navigation(study, case_id):
    """Reference navigation uses bounded text search, then actual source excerpts."""
    study = Path(study)
    case = next(item for item in cases() if item["id"] == case_id)
    expected = next(
        item
        for item in json.loads((study / "manifest.json").read_text())["cases"]
        if item["id"] == case_id
    )
    repository = study / "repos" / case_id
    check_snapshot(repository, expected)
    started = time.perf_counter()
    paths = command(
        ["rg", "--files-with-matches", "--glob", "!.git/**", case["search_pattern"], "."],
        cwd=repository,
    ).splitlines()
    paths = [path.removeprefix("./") for path in paths]
    result = navigation_result(
        repository, case, expected, "source", paths, time.perf_counter() - started
    )
    write_json(study / "navigation" / (case_id + "-source.json"), result)
    return result


def navigation_result(repository, case, expected, mode, paths, elapsed, *, index=None):
    if mode not in MODES:
        raise ValueError("Unknown navigation mode")
    check_snapshot(repository, expected, index)
    authorized = set(expected["files"])
    if not set(paths) <= authorized:
        raise ValueError("Navigation results reference another repository or an unavailable path")
    snippets = [
        {"path": path, "content": (repository / path).read_text()[:12000]}
        for path in dict.fromkeys(paths)
    ]
    found = set(paths) & set(case["expected_files"])
    return {
        "case_id": case["id"],
        "mode": mode,
        "git_sha": expected["git_sha"],
        "navigation_seconds": elapsed,
        "source_bytes": sum(len(item["content"].encode()) for item in snippets),
        "expected_sources": len(case["expected_files"]),
        "found_expected_sources": len(found),
        "source_recall": len(found) / len(case["expected_files"]),
        "retrieval_precision": len(found) / len(set(paths)) if paths else 0,
        "critical_source_omissions": sorted(set(case["expected_files"]) - found),
        "sources": snippets,
        "index": index,
        "input_tokens": None,
        "output_tokens": None,
        "cost": None,
        "inference_performed": False,
    }


def import_index_navigation(study, record):
    """Consume an actual project-scoped MCP observation, then reopen its real files."""
    study = Path(study)
    record = json.loads(Path(record).read_text())
    if record.get("tool") != "codebase-memory-mcp" or not record.get("observations"):
        raise ValueError("A real optional-index tool observation is required")
    case = next(item for item in cases() if item["id"] == record["case_id"])
    expected = next(
        item
        for item in json.loads((study / "manifest.json").read_text())["cases"]
        if item["id"] == case["id"]
    )
    result = navigation_result(
        study / "repos" / case["id"],
        case,
        expected,
        "codebase-memory-mcp",
        record["paths"],
        record["navigation_seconds"],
        index=record,
    )
    write_json(study / "navigation" / (case["id"] + "-codebase-memory-mcp.json"), result)
    return result


def score_response(case, response, review=None):
    """Closed-corpus checks are explicit approximations, not general semantic certification.

    The response text and source references are inspected together; ground-truth
    expressions are withheld from inference inputs. Human review remains required.
    """
    conclusions = response.get("conclusions") or [
        {
            "statement": claim["statement"],
            "status": claim["status"],
            "sources": [
                source["path"] for source in claim.get("sources", []) if source.get("kind") == "git"
            ],
            "details": claim,
        }
        for claim in response.get("claims", [])
    ]
    if not isinstance(conclusions, list) or not conclusions:
        raise ValueError("The response requires explicit conclusions")
    all_text = json.dumps(response, ensure_ascii=False).casefold()
    mentioned_paths = {path for item in conclusions for path in item.get("sources", [])}
    matched = [
        fact["id"]
        for fact in case["critical_facts"]
        if fact["source"] in mentioned_paths
        and all(pattern.casefold() in all_text for pattern in fact["patterns"])
    ]
    errors = []
    for item in conclusions:
        statement = item["statement"].casefold()
        if item.get("status") == "supported" and any(
            value in statement for value in case["forbidden_unqualified_conclusions"]
        ):
            errors.append(item["statement"])
    counterexamples = [
        value for value in case["expected_counterexamples"] if value.casefold() in all_text
    ]
    verified = len(conclusions) - len(errors)
    semantic_precision = None
    semantic_errors = None
    if review:
        if not review.get("reviewer") or not review.get("method"):
            raise ValueError("A semantic review requires an accountable reviewer and method")
        reviewed = review.get("material_conclusions")
        semantic_errors = review.get("material_errors")
        if (
            reviewed != len(conclusions)
            or not isinstance(semantic_errors, int)
            or not 0 <= semantic_errors <= reviewed
        ):
            raise ValueError("Semantic review counts must cover every returned material conclusion")
        semantic_precision = (reviewed - semantic_errors) / reviewed
    return {
        "material_conclusions": len(conclusions),
        "material_errors": semantic_errors,
        "material_error_rate": semantic_errors / len(conclusions)
        if semantic_errors is not None
        else None,
        "precision": semantic_precision,
        "literal_screen_precision": verified / len(conclusions),
        "literal_universal_errors": errors,
        "critical_facts_found": matched,
        "critical_omissions": [
            fact["id"] for fact in case["critical_facts"] if fact["id"] not in matched
        ],
        "counterexamples_detected": counterexamples,
        "unresolved_business_decisions": response.get("unresolved_business_decisions"),
        "scope": "Closed synthetic corpus, literal and source-reference checks plus human review; not general semantic accuracy",
    }


def compare(study, responses=None):
    study = Path(study)
    records = [
        json.loads(path.read_text()) for path in sorted((study / "navigation").glob("*.json"))
    ]
    actual = json.loads(Path(responses).read_text()) if responses else []
    if isinstance(actual, dict):
        actual = actual.get("responses", [])
    for record in records:
        response = next(
            (
                item
                for item in actual
                if item["case_id"] == record["case_id"] and item["mode"] == record["mode"]
            ),
            None,
        )
        record["quality"] = None
        record["analysis_seconds"] = None
        if response:
            if response["git_sha"] != record["git_sha"]:
                raise ValueError("The model response belongs to another source version")
            case = next(item for item in cases() if item["id"] == record["case_id"])
            record["quality"] = score_response(case, response["output"], response.get("review"))
            record.update(
                {
                    name: response.get(name)
                    for name in ("analysis_seconds", "input_tokens", "output_tokens", "cost")
                }
            )
            record["inference_performed"] = True
            record["review"] = response.get("review", {})
    complete = len(records) == 2 * len(cases()) and all(
        record["quality"] is not None
        and record["quality"]["precision"] is not None
        and record["input_tokens"] is not None
        and record["output_tokens"] is not None
        for record in records
    )
    report = {
        "schema_version": 1,
        "corpus": "Three synthetic fixed-SHA Python/TypeScript/Java projects",
        "complete_analysis_comparison": complete,
        "index_enabled_for_production": False,
        "activation_decision": "Keep optional indexing disabled until a reviewed representative paired study proves quality does not regress",
        "measurements": records,
        "limitations": [
            "Small synthetic fixtures are not representative business workloads.",
            "Missing inference usage/cost remains null, never estimated from characters.",
            "Literal scoring requires human semantic review; it is not a universal correctness metric.",
        ],
    }
    write_json(study / "comparison.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "source", "import-index", "compare"])
    parser.add_argument("study", type=Path)
    parser.add_argument("--case")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--responses", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.study)
    elif args.action == "source":
        result = source_navigation(args.study, args.case)
    elif args.action == "import-index":
        result = import_index_navigation(args.study, args.record)
    else:
        result = compare(args.study, args.responses)
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"sources", "observations", "measurements", "cases"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
