"""Public work summaries projected from accepted reports, never runtime transcripts."""

from django.utils.dateparse import parse_datetime

from .sensitive_data import configured_secrets, redact


def waiting_causes(role):
    """Read observed eligibility without probing providers or changing quota state."""
    from .models import AIConnection, AIModel
    from .providers import model_pool_exhausted, quota_exhausted, quota_group

    connections = [item for item in AIConnection.objects.filter(enabled=True).select_related("identity") if role in item.roles]
    if not connections:
        return ["connection_missing"]
    disabled = set(AIModel.objects.filter(enabled=False).values_list("agent", "identifier"))
    reasons = set()
    for item in connections:
        identity = item.identity
        group = list(quota_group(identity)) if identity else []
        statuses = {item.availability, *(member.availability for member in group)}
        if item.status != "CONNECTED" or (identity and identity.status != "CONNECTED") or "AUTH_ERROR" in statuses:
            reasons.add("connection_missing")
        elif (item.agent, item.model) in disabled or "MODEL_UNAVAILABLE" in statuses:
            reasons.add("model_unavailable")
        elif "QUOTA_EXHAUSTED" in statuses or any(quota_exhausted(member) for member in group) or (identity and model_pool_exhausted(item, identity)):
            reasons.add("quota")
        elif "BUSY" in statuses:
            reasons.add("busy")
        elif statuses <= {"AVAILABLE", "UNKNOWN"}:
            # A potentially eligible assistant rules out a connection-wide diagnosis.
            return []
        else:
            reasons.add("unavailable")
    return sorted(reasons)


def progress_snapshot(run, messages):
    """Expose one durable cycle with role completion distinct from correctness."""
    state = run.get("orchestration") or {}
    payload = run.get("job__payload") or {}
    status = run["status"]
    checkpoint = payload.get("next_checkpoint") or state.get("checkpoint", "")
    current = payload.get("current_role") or state.get("waiting_role") or state.get("current_role") or ""
    reason = payload.get("waiting_reason") or state.get("waiting_reason") or ""
    if status == "NEEDS_CLARIFICATION":
        authors = [message.get("attribution") or message.get("data") or {} for message in messages if message.get("kind") in {"clarification", "questions"}]
        current = next((author.get("public_role", "") for author in reversed(authors) if author.get("run_number") == run["number"]), current)
    outputs = state.get("outputs") or {}
    stages = []
    checkpoints = {"analyst": "analyst", "counter_analyst": "comparison", "verifier": "verifier"}
    legacy_roles = {"analyst": {"code"}, "counter_analyst": {"reviewer_writer"}, "verifier": {"synthesis"}}
    for role, completed_checkpoint in checkpoints.items():
        output = outputs.get(completed_checkpoint) or {}
        complete = bool(output) and not output.get("questions")
        if role == "counter_analyst" and output.get("verification"):
            complete = complete and bool(outputs.get("focused_verification"))
        if not output and state.get("version") not in {"2.3", "2.4"}:
            complete = any(step.get("status") == "DONE" and step.get("public_role") == role and legacy_roles[role].intersection(step.get("roles", [])) for step in run.get("steps", []))
        running = next((step for step in reversed(run.get("steps", [])) if step.get("public_role") == role and step.get("status") == "RUNNING"), None)
        if status == "NEEDS_CLARIFICATION" and current == role:
            stage = "clarification"
        elif running and checkpoint != "writer" and status not in {"ERROR", "CANCELLED", "READY", "PARTIAL", "NEEDS_CLARIFICATION"}:
            stage = "running"
        elif complete:
            stage = "done"
        elif role == current and status in {"ERROR", "CANCELLED"}:
            stage = "error" if status == "ERROR" else "cancelled"
        elif role == current and status == "QUEUED":
            stage = "blocked" if reason else "waiting"
        elif status in {"READY", "PARTIAL", "ERROR", "CANCELLED"}:
            stage = "unknown"
        else:
            stage = "waiting"
        stages.append({"role": role, "status": stage})
    causes = waiting_causes(current) if status == "QUEUED" and reason and current else []
    return {"status": status, "current_role": current, "checkpoint": checkpoint,
            "waiting_reason": reason, "waiting_causes": causes, "stages": stages,
            "all_stages_done": all(stage["status"] == "done" for stage in stages)}


def _questions(value):
    """Compare actual question identities/text, ignoring unrelated schema defaults."""
    if not isinstance(value, list) or not value:
        return ()
    return tuple(sorted(
        (str(question.get("id", "")), str(question.get("question", "")).strip())
        for question in value if isinstance(question, dict)
    ))


def _time(value):
    if hasattr(value, "timestamp"):
        return value.timestamp()
    try:
        parsed = parse_datetime(value or "")
        return parsed.timestamp() if parsed and parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def attribute_messages(messages, runs):
    """Recover historical authors from matching questions and accepted step intervals.

    This only enriches the response. Stored messages and execution snapshots stay
    immutable; current connection settings never determine a historical author.
    Missing or contradictory evidence leaves attribution unknown.
    """
    for message in messages:
        if message.get("role") != "assistant" or message.get("kind") not in {"questions", "clarification"}:
            continue
        data = message.get("data") or {}
        signature = _questions(data.get("questions"))
        at = _time(message.get("created_at"))
        if not signature or at is None:
            continue
        previous_user = max((
            stamp for item in messages
            if item.get("role") == "user" and (stamp := _time(item.get("created_at"))) is not None and stamp <= at
        ), default=float("-inf"))
        matches = []
        for run in runs:
            if data.get("run_number") is not None and data["run_number"] != run["number"]:
                continue
            state = run.get("orchestration") or {}
            reports = list(state.get("structured_outputs", []))
            accepted = [step for step in run.get("steps", []) if step.get("status") == "DONE"]
            if reports and (
                len(reports) != len(accepted) or any(
                    report.get("roles") != step.get("roles")
                    or (report.get("public_role") and report["public_role"] != step.get("public_role"))
                    for report, step in zip(reports, accepted, strict=True)
                )
            ):
                # An incomplete report ledger cannot establish positional authorship.
                continue
            paired_steps = {id(report): step for report, step in zip(reports, accepted)}
            for checkpoint, output in (() if reports else state.get("outputs", {}).items()):
                role = {
                    "requirement": "analyst", "attachments": "analyst", "analyst": "analyst",
                    "counter_independent": "counter_analyst", "comparison": "counter_analyst",
                    "focused_verification": "counter_analyst", "verifier": "verifier",
                }.get(checkpoint)
                reports.append({"public_role": role, "output": output})
            matching_reports = []
            for report in reports:
                output = report.get("output") or {}
                for owner in (output, output.get("analysis"), output.get("review")):
                    if isinstance(owner, dict) and _questions(owner.get("questions")) == signature:
                        matching_reports.append(report)
                        break
            candidates = []
            for step in run.get("steps", []):
                started, finished = _time(step.get("started_at")), _time(step.get("finished_at"))
                if step.get("status") != "DONE" or started is None or finished is None:
                    continue
                if not previous_user <= started <= finished <= at:
                    continue
                role = step.get("public_role")
                if data.get("public_role") and data["public_role"] != role:
                    continue
                if not any(
                    (paired_steps.get(id(report)) is step if paired_steps else (
                        (report.get("public_role") == role and role)
                        or (not report.get("public_role") and report.get("roles") and report["roles"] == step.get("roles"))
                    ))
                    for report in matching_reports
                ):
                    continue
                candidates.append((finished, step))
            if not candidates:
                continue
            latest = max(finished for finished, _ in candidates)
            latest_steps = [step for finished, step in candidates if finished == latest]
            if len(latest_steps) != 1:
                continue
            step = latest_steps[0]
            matches.append({
                "run_number": run["number"], "public_role": step.get("public_role") or "",
                "provider": step.get("provider") or step.get("agent") or "",
                "connection_name": step.get("connection_name") or "",
                "model": step.get("model") or "", "context_id": step.get("context_id") or "",
                "attempt_id": step.get("attempt_id") or "", "source": "recorded_history",
            })
        if len(matches) == 1:
            message["attribution"] = matches[0]


def role_reviews(state):
    """Whitelist final report fields; private prompts and reasoning stay excluded."""
    reviews = []
    for checkpoint, role in (
        ("analyst", "analyst"),
        ("counter_independent", "counter_analyst"),
        ("comparison", "counter_analyst"),
        ("focused_verification", "counter_analyst"),
        ("verifier", "verifier"),
    ):
        output = state.get("outputs", {}).get(checkpoint)
        if not isinstance(output, dict):
            continue
        report = output.get("report") or output
        claims = report.get("claims", [])
        reviews.append({
            "checkpoint": checkpoint,
            "public_role": role,
            "summary": output.get("summary") or output.get("current_behavior") or "",
            "findings": [
                {key: claim[key] for key in ("statement", "status", "kind", "sources") if key in claim}
                for claim in claims if isinstance(claim, dict) and claim.get("statement")
            ],
            "issues": output.get("issues", []) + output.get("divergences", []),
            "agreements": output.get("agreements", []),
            "limits": report.get("limitations", []) + output.get("uncertainties", [])
            + output.get("remaining_uncertainties", []),
        })
    return redact(reviews, configured_secrets()) if reviews else []
