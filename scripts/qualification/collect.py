"""Collect actual application observations without invoking or scoring an AI agent."""

import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

from .harness import check_study, digest, read_json, write_json


def validate_request(packet, request, *, admission=False):
    """Do not attribute another request or Git baseline to a frozen case."""
    if any(getattr(request, key) != packet[key] for key in ("need", "workflow", "language")):
        raise ValueError("The application request differs from its frozen case")
    expected = {row["id"]: row["git_sha"] for row in packet["repositories"]}
    sources = request.baseline
    database_available = bool(request.database_snapshot)
    if admission:
        if request.environment_id is None or request.scope_assessment.get("context_revision") != request.environment.context_revision:
            raise ValueError("The admission context is unavailable or changed")
        sources = list(request.environment.repositories.values("repository", "sha"))
        database_available = bool(request.environment.database_id)
    actual = {row["repository"].rsplit("/", 1)[-1]: row["sha"] for row in sources}
    if actual != expected or len(actual) != len(sources):
        raise ValueError("The application's source baseline differs from the frozen Git inputs")
    if database_available != (packet["database"]["state"] == "available"):
        raise ValueError("The application's database availability differs from the frozen case")
    attachments = []
    for row in request.attachments.all():
        path = Path(row.path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("A frozen request attachment is unavailable or oversized")
        attachments.append(hashlib.sha256(path.read_bytes()).hexdigest())
    if sorted(attachments) != sorted(row["sha256"] for row in packet["attachments"]):
        raise ValueError("The application's attachments differ from the frozen case")


def observed_attempts(steps, cli_versions):
    """Use persisted invocation observations, including failed calls and repairs."""
    result = []
    for step in steps:
        if not step.get("attempts"):
            continue
        provider = step.get("provider")
        version = cli_versions.get(provider, {})
        if not version.get("version") or not version.get("observed_at") or not version.get("source"):
            raise ValueError("Record actual CLI version observations separately from expected configuration")
        result.append({
            "role": step["public_role"], "phase": step.get("roles", []),
            "context_id": step.get("context_id"), "provider": provider,
            "model": step.get("model"), "family": step.get("model_family"),
            "cli_version": version["version"], "effort": step.get("effort"),
            "status": "SUCCESS" if step.get("status") == "DONE" else step.get("status", "UNKNOWN"),
            "failure": step.get("failure"), "calls": step["attempts"],
            "usage": step.get("usage", {}),
            "usage_observations": step.get("usage_observations", []),
            "started_at": step.get("started_at"), "finished_at": step.get("finished_at"),
            "elapsed_seconds": invocation_seconds(step),
        })
    return result


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else None


def invocation_seconds(step):
    started, finished = timestamp(step.get("started_at")), timestamp(step.get("finished_at"))
    if started is None or finished is None:
        return None
    if finished < started:
        raise ValueError("Invocation timestamps are inconsistent")
    return (finished - started).total_seconds()


def collect_request(packet, request, frozen, protocol, cli_versions):
    run = request.analysis_runs.order_by("-number").first()
    if run is None and request.scope_assessment.get("status") in {"OUT_OF_SCOPE", "NEEDS_CLARIFICATION"}:
        from core.models import Job

        validate_request(packet, request, admission=True)
        assessed = timestamp(request.scope_assessment.get("assessed_at"))
        if assessed is None or assessed < request.created_at or Job.objects.filter(kind="analysis", target=str(request.pk)).exists():
            raise ValueError("Admission-only measurement requires its timestamp and proof that no analysis job exists")
        return {
            "case_id": packet["case_id"], "packet_sha256": frozen["packet_sha256"],
            "request_id": str(request.pk), "status": "PARTIAL", "application_status": request.status,
            "scope_status": request.scope_assessment["status"], "attempts": [],
            "elapsed_seconds": (assessed - request.created_at).total_seconds(),
            "execution_seconds": 0.0,
            "output": {"application_status": request.status, "scope_assessment": request.scope_assessment, "result": None},
        }
    validate_request(packet, request)
    if run is None or run.started_at is None:
        return None
    configuration = run.orchestration.get("config", {})
    expected = protocol["instructions"].get("application_config")
    if expected and any(configuration.get(key) != value for key, value in expected.items()):
        raise ValueError("The application used different frozen orchestration settings")
    expected_agents = protocol["instructions"].get("agent_definitions")
    library = run.context_snapshot.get("library", {})
    if expected_agents is not None and (
        library.get("agents") != expected_agents or library.get("skills") != protocol["skills"]
    ):
        raise ValueError("The application used different frozen agent or skill definitions")
    version = request.versions.filter(run=run).order_by("-number").first()
    output = {
        "application_status": request.status, "questions": request.questions,
        "error": request.error, "warnings": run.warnings,
        "result": None if version is None else {
            "number": version.number, "status": version.status,
            "ticket": version.ticket, "explanation": version.explanation,
            "business_summary": version.business_summary, "evidence": version.evidence,
            "artifacts": {row.name: row.content for row in version.artifacts.all()},
        },
        "observations": run.orchestration.get("outputs", {}),
        "database_checks": run.orchestration.get("database_checks", []),
        "context_sha256": run.context_snapshot.get("sha256"),
    }
    complete = request.status == "READY" and version is not None and version.status == "READY"
    finished = run.finished_at
    finish_source = "analysis_run" if finished else None
    # A legitimate clarification or a failed required stage is an observed partial
    # outcome. Running work is not a completed quality measurement.
    terminal = request.status in {"READY", "PARTIAL", "ERROR", "CANCELLED", "NEEDS_CLARIFICATION"}
    if terminal and finished is None:
        # Interrupted incremental runs may resume later; their run-level finish
        # remains empty. The failed step still records the actual interruption.
        ends = [timestamp(step.get("finished_at")) for step in run.steps]
        finished = max((value for value in ends if value is not None), default=None)
        if finished is None:
            raise ValueError("A terminal observation needs a persisted finish timestamp")
        finish_source = "last_persisted_step"
    end = finished or datetime.now(run.started_at.tzinfo)
    if end < run.started_at:
        raise ValueError("Analysis timestamps are inconsistent")
    attempts = observed_attempts(run.steps, cli_versions)
    execution_seconds = [attempt["elapsed_seconds"] for attempt in attempts]
    return {
        "case_id": packet["case_id"], "packet_sha256": frozen["packet_sha256"],
        "request_id": str(request.pk), "run_number": run.number,
        "status": "COMPLETE" if complete else "PARTIAL" if terminal else "RUNNING",
        "application_status": request.status,
        "scope_status": request.scope_assessment.get("status"),
        "elapsed_seconds": (end - run.started_at).total_seconds(),
        "execution_seconds": sum(execution_seconds) if execution_seconds and all(value is not None for value in execution_seconds) else None,
        "finished_at_source": finish_source,
        "attempts": attempts, "output": output,
    }


def collect(study, configuration_id, bindings, cli_versions):
    """Read existing application runs; scope-only cases use the actual pure policy."""
    from core.models import Request
    from core.scope_policy import classify

    manifest, protocol, _, _ = check_study(study)
    if configuration_id not in {row["id"] for row in protocol["configurations"]}:
        raise ValueError("Unknown frozen configuration")
    known = {row["id"] for row in manifest["cases"]}
    if not set(bindings) <= known or len(set(bindings.values())) != len(bindings):
        raise ValueError("Bind each application request to at most one known corpus case")
    rows = []
    for frozen in manifest["cases"]:
        packet = read_json(Path(study) / "packets" / frozen["id"] / "packet.json")
        if packet["kind"] == "scope":
            started = time.perf_counter()
            decision = classify(packet["need"], environment=packet["environment"], language=packet["language"])
            rows.append({
                "case_id": packet["case_id"], "packet_sha256": frozen["packet_sha256"],
                "status": "COMPLETE", "scope_status": decision["status"],
                "elapsed_seconds": time.perf_counter() - started,
                "attempts": [], "output": decision,
            })
        elif packet["case_id"] in bindings:
            request = Request.objects.get(pk=bindings[packet["case_id"]])
            row = collect_request(packet, request, frozen, protocol, cli_versions)
            if row:
                rows.append(row)
    return json.loads(json.dumps({
        "configuration_id": configuration_id, "manifest_sha256": digest(manifest),
        "cli_observations": cli_versions, "cases": rows,
    }, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--cli-versions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    result = collect(args.study, args.configuration, read_json(args.bindings), read_json(args.cli_versions))
    write_json(args.output, result)
    print(json.dumps({"observed_cases": len(result["cases"]), "configuration_id": args.configuration}))


if __name__ == "__main__":
    main()
