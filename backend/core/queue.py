"""Read the existing queue without claiming work or changing its scheduling policy."""

from uuid import UUID

from .models import AIConnection, AnalysisRun, Environment, Job, PublishedTicket, Request

RECENT_LIMIT = 15


def assignments_for(job, run):
    """Use execution snapshots, never a configuration edited after the run."""
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
    if job.status == "RUNNING" and run and run.orchestration.get("version") == "1.5":
        active = [step for step in run.steps if step.get("status") == "RUNNING"]
        if active:
            step = active[-1]
            recorded = [
                {
                    "connection_id": step.get("connection_id"),
                    "connection_name": step.get("connection_name", ""),
                    "agent": step.get("provider", ""),
                    "model": step.get("model", ""),
                    "public_role": step.get("public_role", ""),
                    "model_family": step.get("model_family", ""),
                }
            ]
        elif job.payload.get("current_assignment"):
            recorded = [job.payload["current_assignment"]]
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


def snapshot():
    jobs = list(Job.objects.filter(status__in=["RUNNING", "QUEUED"]).order_by("created_at", "id"))
    jobs += list(
        Job.objects.exclude(status__in=["RUNNING", "QUEUED"]).order_by(
            "-finished_at", "-created_at", "-id"
        )[:RECENT_LIMIT]
    )
    request_ids = []
    for job in jobs:
        if job.kind == "analysis":
            try:
                request_ids.append(UUID(job.target))
            except (ValueError, TypeError, AttributeError):
                pass
    requests = {
        str(item.pk): item
        for item in Request.objects.filter(pk__in=request_ids).select_related("environment")
    }
    environment_ids = [int(j.target) for j in jobs if j.kind == "sync" and j.target.isdecimal()]
    environments = {str(e.pk): e for e in Environment.objects.filter(pk__in=environment_ids)}
    runs = {r.job_id: r for r in AnalysisRun.objects.filter(job_id__in=[j.pk for j in jobs])}
    agents = dict(AIConnection.objects.values_list("id", "agent"))
    values, position = [], 0
    for job in jobs:
        if job.status == "QUEUED":
            position += 1
        item = requests.get(job.target)
        environment = item.environment if item else environments.get(job.target)
        run = runs.get(job.pk)
        assignments = assignments_for(job, run)
        provider_names = list(
            dict.fromkeys(
                step["provider"] for step in (run.steps if run else []) if step.get("provider")
            )
        ) or [agents[pk] for pk in job.payload.get("connection_ids", []) if pk in agents]
        values.append(
            {
                "id": job.pk,
                "kind": job.kind,
                "status": job.status,
                "request_id": str(item.pk) if item else None,
                "environment_id": environment.pk if environment else None,
                "title": item.need[:180] if item else environment.name if environment else "Task",
                "environment_name": (item.environment_name_snapshot if item else "")
                or (environment.name if environment else ""),
                "operation": "Analysis" if job.kind == "analysis" else "Synchronization",
                "agent": (", ".join(provider_names) or None) if job.status != "QUEUED" else None,
                "assignments": assignments,
                "public_role": (
                    run.orchestration.get("waiting_role")
                    if job.status == "QUEUED"
                    else run.orchestration.get("current_role")
                )
                if run
                else None,
                "warnings": run.warnings if run else [],
                "waiting_reason": (
                    run.orchestration.get("waiting_reason") or job.payload.get("waiting_reason", "")
                )
                if run and job.status == "QUEUED"
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
                "href": f"/requests/{item.pk}" if item else "/admin",
            }
        )
    publications = list(
        PublishedTicket.objects.filter(status="PUBLISHING").select_related("version", "request")
    )
    publications += list(
        PublishedTicket.objects.exclude(status="PUBLISHING")
        .select_related("version", "request")
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
                "href": f"/requests/{publication.request_id}?version={publication.version.number}",
            }
        )
    ordered = sorted(
        values,
        key=lambda value: (
            {"RUNNING": 0, "QUEUED": 1}.get(value["status"], 2),
            value["queue_position"] or 0
            if value["status"] in {"RUNNING", "QUEUED"}
            else -(value["finished_at"] or value["created_at"]).timestamp(),
        ),
    )
    active = [value for value in ordered if value["status"] in {"RUNNING", "QUEUED"}]
    recent = [value for value in ordered if value["status"] not in {"RUNNING", "QUEUED"}]
    return active + recent[:RECENT_LIMIT]
