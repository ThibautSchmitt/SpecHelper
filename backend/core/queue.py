"""Read the existing queue without claiming work or changing its scheduling policy."""

from uuid import UUID

from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    AIConnection,
    AnalysisRun,
    Environment,
    Job,
    PublishedTicket,
    Request,
    RequestMessage,
    ResultVersion,
)

RECENT_LIMIT = 15


def analysis_timing(job, run, paused, now):
    """Report recorded AI intervals; wall time includes user/resource waits."""
    intervals = []
    for step in (run.steps if run else []):
        try:
            start = parse_datetime(step.get("started_at") or "")
            end = parse_datetime(step.get("finished_at") or "")
        except (TypeError, ValueError):
            continue
        if not end and job.status == "RUNNING" and step.get("status") == "RUNNING":
            end = now
        if start and end and timezone.is_aware(start) and timezone.is_aware(end) and end >= start:
            intervals.append((start, end))
    # Merge overlaps so one recorded interval cannot be counted twice.
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return {
        "active_analysis_seconds": int(sum((end-start).total_seconds() for start, end in merged)) if merged else None,
        "clarification_since": ((run.finished_at if run else None) or job.finished_at) if paused else None,
        # A resumed job has no reliable timestamp for its latest queue admission.
        "queued_since": job.created_at if job.status == "QUEUED" and not job.started_at else None,
    }


def assignments_for(job, run):
    """Use execution snapshots, never a configuration edited after the run."""
    if job.kind == "library_assistant":
        return (
            []
            if job.status == "QUEUED"
            else [
                {
                    key: item.get(key, "")
                    for key in (
                        "connection_id",
                        "connection_name",
                        "agent",
                        "model",
                        "public_role",
                        "model_family",
                    )
                }
                for item in job.payload.get("assignments", [])
            ]
        )
    if job.kind != "analysis" or job.status == "QUEUED":
        return []
    recorded = [
        {
            "connection_id": step.get("connection_id"),
            "connection_name": step.get("connection_name", ""),
            "agent": step.get("provider", step.get("agent", "")),
            "model": step.get("model", ""),
            "public_role": step.get("public_role", ""),
            "model_family": step.get("model_family", ""),
        }
        for step in (run.steps if run else [])
        if step.get("connection_id") or step.get("connection_name")
    ]
    if not recorded:
        recorded = job.payload.get("assignments", [])
    current = current_assignment(job, run)
    if current:
        recorded = [current]
    values, seen = [], set()
    for item in recorded:
        value = {
            key: item.get(key)
            for key in (
                "connection_id",
                "connection_name",
                "agent",
                "model",
                "public_role",
                "model_family",
            )
        }
        value["public_role"] = value["public_role"] or item.get("role", "")
        value["model_family"] = value["model_family"] or item.get("family", "")
        key = tuple(value.values())
        if key not in seen:
            seen.add(key)
            values.append(value)
    return values


def current_assignment(job, run):
    """Only mark an executing step or a newly reserved session as current."""
    if job.kind == "library_assistant" and job.status == "RUNNING":
        return next(iter(assignments_for(job, run)), None)
    if job.kind != "analysis" or job.status != "RUNNING" or not run:
        return None
    active = [step for step in run.steps if step.get("status") == "RUNNING"]
    if active:
        step = active[-1]
        return {**step, "agent": step.get("provider", step.get("agent", ""))}
    reserved = job.payload.get("current_assignment")
    if reserved and (
        not run.steps
        or (
            reserved.get("context_id")
            and not any(step.get("context_id") == reserved["context_id"] for step in run.steps)
        )
    ):
        return reserved
    return None


def execution_state(job, run):
    """Distinguish a live execution from retained historical assignment evidence."""
    if current_assignment(job, run):
        return "current"
    return "previous" if assignments_for(job, run) else "unassigned"


def result_state(job, run):
    """A completed process is not evidence of a complete independently checked result."""
    if job.kind != "analysis":
        return {"result_status": None, "result_limits": []}
    evidence = run.orchestration.get("evidence", {}) if run else {}
    limits = list(evidence.get("limitations", []))
    limits.extend(
        claim.get("verification_notes", claim.get("statement", ""))
        for claim in evidence.get("claims", [])
        if claim.get("material", True) and claim.get("status") != "supported"
    )
    roles = {
        step.get("public_role")
        for step in (run.steps if run else [])
        if step.get("status") == "DONE"
    }
    if job.status in {"RUNNING", "QUEUED"} or (run and run.status == "NEEDS_CLARIFICATION"):
        state = "pending"
    elif not run or run.status in {"ERROR", "CANCELLED"}:
        state = "unusable"
    elif run.status == "PARTIAL" or evidence.get("blocking"):
        state = "partial"
    elif (
        run.request.analysis_protocol in {"2.3", "2.4"}
        and not {"analyst", "counter_analyst", "verifier"} <= roles
    ):
        state = "partial"
        limits.append("Independent analysis, counter-analysis and verification are required.")
    else:
        state = "complete" if run.status in {"READY", "DONE"} else "pending"
    return {
        "result_status": state,
        "result_limits": list(dict.fromkeys(value for value in limits if value))[:30],
    }


def snapshot():
    latest_analysis = Job.objects.filter(kind="analysis", target=OuterRef("target")).order_by(
        "-created_at", "-id"
    )
    visible = Job.objects.filter(
        ~Q(kind="analysis") | Q(pk=Subquery(latest_analysis.values("pk")[:1]))
    )
    jobs = list(visible.filter(status__in=["RUNNING", "QUEUED"]).order_by("created_at", "id"))
    jobs += list(
        visible.exclude(status__in=["RUNNING", "QUEUED"])
        .exclude(kind="sync", status="DONE")
        .order_by("-finished_at", "-created_at", "-id")[:RECENT_LIMIT]
    )
    # Clarification is not a scheduler state: retain its latest completed job even
    # when it falls outside the bounded terminal history, without creating work.
    latest_job = Job.objects.filter(kind="analysis", target=OuterRef("target")).order_by(
        "-created_at", "-id"
    )
    paused_jobs = Job.objects.filter(
        kind="analysis",
        target__in=[
            str(pk)
            for pk in Request.objects.filter(status="NEEDS_CLARIFICATION").values_list(
                "pk", flat=True
            )
        ],
    ).filter(pk=Subquery(latest_job.values("pk")[:1]))
    paused_jobs = list(paused_jobs)
    paused_ids = {job.pk for job in paused_jobs}
    seen = {job.pk for job in jobs}
    jobs += [job for job in paused_jobs if job.pk not in seen]
    request_ids = []
    for job in jobs:
        if job.kind == "analysis":
            try:
                request_ids.append(UUID(job.target))
            except (ValueError, TypeError, AttributeError):
                pass
    revisions = RequestMessage.objects.filter(request_id=OuterRef("pk"), kind="need_revision").order_by("-created_at")
    requests = {
        str(item.pk): item
        for item in Request.objects.filter(pk__in=request_ids).select_related("environment").annotate(
            last_need_revision=Subquery(revisions.values("created_at")[:1]),
        )
    }
    environment_ids = [int(j.target) for j in jobs if j.kind == "sync" and j.target.isdecimal()]
    environments = {str(e.pk): e for e in Environment.objects.filter(pk__in=environment_ids)}
    runs = {r.job_id: r for r in AnalysisRun.objects.filter(job_id__in=[j.pk for j in jobs]).select_related("request")}
    latest_versions = ResultVersion.objects.filter(request_id=OuterRef("request_id")).order_by("-number")
    versions = {
        str(version.request_id): version
        for version in ResultVersion.objects.filter(
            request_id__in=request_ids, pk=Subquery(latest_versions.values("pk")[:1]),
        ).only("id", "request_id", "status", "evidence", "created_at")
    }
    published = set(PublishedTicket.objects.filter(status="PUBLISHED", version_id__in=[v.pk for v in versions.values()]).values_list("version_id", flat=True))
    agents = dict(AIConnection.objects.values_list("id", "agent"))
    values, position = [], 0
    for job in jobs:
        if job.status == "QUEUED":
            position += 1
        item = requests.get(job.target)
        environment = item.environment if item else environments.get(job.target)
        run = runs.get(job.pk)
        assignments = assignments_for(job, run)
        assignment_state = execution_state(job, run)
        paused = (
            job.kind == "analysis"
            and item
            and item.status == "NEEDS_CLARIFICATION"
            and job.status == "DONE"
            and job.pk in paused_ids
        )
        queue_state = "PAUSED" if paused else job.status
        incremental = bool(item and item.analysis_protocol == "2.4")
        if incremental and job.status == "QUEUED":
            queue_state = "WAITING_AI"
        public_role = (
            (current_assignment(job, run) or {}).get("public_role")
            or job.payload.get("current_role")
            or "analyst"
        )
        elapsed_start = run.started_at if run and run.started_at else job.started_at
        elapsed_end = (run.finished_at if run else None) or job.finished_at or timezone.now()
        progress = item.progress[-1].get("label", "") if item and item.progress else ""
        stage = (progress or "Analysis in progress") if job.status == "RUNNING" else ""
        if paused:
            stage = "Your answer is needed"
        elif job.status == "QUEUED":
            stage = "Waiting for a worker"
        elif job.status == "DONE":
            stage = "Analysis completed" if job.kind == "analysis" else "Synchronization completed"
        elif job.kind == "sync" and job.status == "RUNNING":
            stage = "Synchronizing repositories"
        if job.kind == "library_assistant":
            stage = {
                "RUNNING": "Testing the draft in a sandbox"
                if job.payload.get("operation") == "test"
                else "Preparing a library proposal",
                "QUEUED": "Waiting for the selected AI connection",
                "DONE": "Sandbox demonstration completed"
                if job.payload.get("operation") == "test"
                else "Library proposal ready for review",
            }.get(job.status, "")
            if job.status == "DONE" and job.payload.get("outcome") == "NEEDS_CLARIFICATION":
                stage = "Your answer is needed"
        provider_names = list(
            dict.fromkeys(
                step["provider"] for step in (run.steps if run else []) if step.get("provider")
            )
        ) or [agents[pk] for pk in job.payload.get("connection_ids", []) if pk in agents]
        if assignment_state == "current":
            provider_names = list(dict.fromkeys(a["agent"] for a in assignments if a["agent"]))
        values.append(
            {
                **result_state(job, run),
                **(analysis_timing(job, run, paused, timezone.now()) if job.kind == "analysis" else {}),
                "analysis_state": None,
                "id": job.pk,
                "kind": job.kind,
                "workflow": item.workflow if item else None,
                "status": job.status,
                "queue_state": queue_state,
                "assignment_state": assignment_state,
                "stage_number": {"analyst": 1, "counter_analyst": 2, "verifier": 3}.get(
                    public_role, 1
                )
                if incremental
                else None,
                "stage_count": 3 if incremental else None,
                "elapsed_seconds": max(0, int((elapsed_end - elapsed_start).total_seconds()))
                if elapsed_start
                else 0,
                "can_cancel": bool(incremental and job.status in {"QUEUED", "RUNNING"}),
                "can_retry": bool(
                    incremental
                    and job.status in {"ERROR", "CANCELLED"}
                    and not job.payload.get("connection_ids")
                ),
                "stage": stage,
                "pause_reason": "A business answer is needed." if paused else "",
                "executor_name": "Git synchronization" if job.kind == "sync" else None,
                "request_id": str(item.pk) if item else None,
                "environment_id": environment.pk if environment else None,
                "title": item.need[:180]
                if item
                else environment.name
                if environment
                else job.payload.get("title", "Task"),
                "environment_name": (item.environment_name_snapshot if item else "")
                or (environment.name if environment else ""),
                "operation": (
                    "Question analysis" if item and item.workflow == "question" else "Analysis"
                )
                if job.kind == "analysis"
                else (
                    "Library sandbox test"
                    if job.payload.get("operation") == "test"
                    else "Library generation"
                )
                if job.kind == "library_assistant"
                else "Synchronization",
                "agent": (", ".join(provider_names) or None)
                if job.kind in {"analysis", "library_assistant"} and job.status != "QUEUED"
                else None,
                "assignments": assignments,
                "public_role": (
                    assignments[0].get("public_role")
                    if assignment_state == "current" and assignments
                    else None
                )
                or (
                    run.orchestration.get("waiting_role")
                    if job.status == "QUEUED"
                    else run.orchestration.get("current_role")
                )
                if run
                else job.payload.get("current_role")
                if job.kind == "library_assistant"
                else None,
                "warnings": run.warnings if run else [],
                "waiting_reason": (
                    run.orchestration.get("waiting_reason") or job.payload.get("waiting_reason", "")
                )
                if run and job.status == "QUEUED"
                else job.payload.get("waiting_reason", "")
                if job.kind == "library_assistant"
                else "",
                "connection_name": ", ".join(
                    dict.fromkeys(a["connection_name"] for a in assignments if a["connection_name"])
                )
                or None,
                "model": ", ".join(dict.fromkeys(a["model"] for a in assignments if a["model"]))
                or None,
                "request_status": item.status if item else None,
                "queue_position": position if job.status == "QUEUED" else None,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "error": job.error,
                "href": f"/analyses/{item.pk}"
                if item
                else f"/admin?library_draft={job.target}&library_kind={job.payload.get('draft_kind', 'agent')}"
                if job.kind == "library_assistant"
                else "/admin",
            }
        )
        if item:
            from .analysis_states import result_state as business_state

            version = versions.get(str(item.pk))
            evidence = version.evidence if version else {}
            values[-1]["analysis_state"] = business_state(
                item.status, item.workflow, latest_status=version.status if version else None,
                published=bool(version and version.pk in published),
                incomplete=bool(evidence.get("blocking")),
                stale=bool(version and item.last_need_revision and item.last_need_revision > version.created_at),
                verification_unavailable=bool(evidence.get("blocking") and evidence.get("database", {}).get("status") == "unavailable"),
                scope_clarification=item.scope_assessment.get("status") == "NEEDS_CLARIFICATION",
            )
            if values[-1]["result_status"] == "partial" and values[-1]["analysis_state"] in {"draft_ready", "completed", "saved"}:
                values[-1]["analysis_state"] = "partial"
            if values[-1]["analysis_state"] in {"partial", "verification_unavailable"}:
                values[-1]["result_status"] = "partial"
            if values[-1]["result_status"] == "partial" and not values[-1]["result_limits"]:
                values[-1]["result_limits"] = evidence.get("limitations", [])[:30]
    publications = list(
        PublishedTicket.objects.filter(status="PUBLISHING").select_related(
            "version", "request", "connector"
        )
    )
    publications += list(
        PublishedTicket.objects.exclude(status="PUBLISHING")
        .select_related("version", "request", "connector")
        .order_by("-finished_at", "-created_at")[:RECENT_LIMIT]
    )
    for publication in publications:
        state = publication.observed_status
        stale = state != publication.status
        values.append(
            {
                "id": "publication:" + str(publication.pk),
                "kind": "publication",
                "status": {"PUBLISHING": "RUNNING", "PUBLISHED": "DONE"}.get(state, "ERROR"),
                "publication_status": state,
                "queue_state": {"PUBLISHING": "RUNNING", "PUBLISHED": "DONE"}.get(state, "ERROR"),
                "assignment_state": "unassigned",
                "executor_name": publication.connector.name,
                "stage": "Publishing ticket"
                if state == "PUBLISHING"
                else "Ticket published"
                if state == "PUBLISHED"
                else "",
                "pause_reason": "",
                "request_id": str(publication.request_id),
                "environment_id": publication.request.environment_id,
                "title": publication.title,
                "environment_name": publication.version.environment_name,
                "operation": "Ticket publication",
                "agent": None,
                "assignments": [],
                "public_role": None,
                "warnings": [],
                "waiting_reason": "",
                "connection_name": None,
                "model": None,
                "request_status": None,
                "queue_position": None,
                "created_at": publication.created_at,
                "started_at": None if stale else publication.created_at,
                "finished_at": publication.finished_at,
                "error": publication.error
                or (
                    "Publication status is uncertain. Check the destination before retrying."
                    if stale
                    else ""
                ),
                "href": f"/analyses/{publication.request_id}?version={publication.version.number}",
            }
        )
    ordered = sorted(
        values,
        key=lambda value: (
            {"RUNNING": 0, "QUEUED": 1, "WAITING_AI": 1, "PAUSED": 2, "DONE": 3, "ERROR": 3}.get(
                value["queue_state"], 5
            ),
            value["queue_position"] or 0
            if value["status"] in {"RUNNING", "QUEUED"}
            else -(value["finished_at"] or value["created_at"]).timestamp(),
        ),
    )
    active = [
        value
        for value in ordered
        if value["queue_state"] in {"RUNNING", "QUEUED", "WAITING_AI", "PAUSED"}
    ]
    recent = [
        value
        for value in ordered
        if value["queue_state"] not in {"RUNNING", "QUEUED", "WAITING_AI", "PAUSED"}
    ]
    return active + recent[:RECENT_LIMIT]
