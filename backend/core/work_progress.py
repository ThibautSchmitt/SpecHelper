"""Fenced public observations in the existing job, separate from agent evidence."""

import copy
import hashlib
import json
import logging
import time
import uuid
from typing import Literal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import AIConnection, Job, StepExecution
from .progress_text import safe_prefix
from .sensitive_data import configured_secrets, redact

Operation = Literal[
    "preparing",
    "processing",
    "search",
    "read",
    "git",
    "command",
    "tool",
    "plan",
    "reference",
    "writing",
]


class WorkEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{20}$")
    operation: Operation
    state: Literal["running", "done", "error"]
    observed_at: str = Field(max_length=40)


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["progress"]
    sequence: int = Field(ge=1, le=1000000000)
    activity: Operation
    events: list[WorkEvent] = Field(max_length=24)
    preview: str = Field(default="", max_length=12000)


class Recorder:
    """One HTTP invocation; raw frames never become prompts or verified findings."""

    def __init__(self, job, attempt, role, checkpoint, execution=None):
        self.job_id, self.target, self.attempt = job.pk, job.target, attempt
        self.role, self.checkpoint, self.execution = role, checkpoint, execution
        self.id, self.sequence, self.pending = str(uuid.uuid4()), 0, None
        self.last_write, self.secrets = 0, configured_secrets()
        self.closed = False

    @classmethod
    def for_payload(cls, payload):
        if not payload.get("attempt_id"):
            return None
        step = (
            StepExecution.objects.select_related("job")
            .filter(attempt_id=payload["attempt_id"], status="RUNNING")
            .first()
        )
        if step and step.job.target == payload.get("request_id") and step.job.status == "RUNNING":
            return cls(step.job, str(step.attempt_id), step.public_role, step.checkpoint, step.pk)
        job = Job.objects.filter(
            kind="discussion",
            target=payload.get("request_id"),
            status="RUNNING",
            payload__attempt_id=payload["attempt_id"],
        ).first()
        if job:
            return cls(job, payload["attempt_id"], "discussion", "discussion")
        return None

    def preview_field(self, payload):
        if self.role == "discussion":
            return "message"
        if self.checkpoint == "writer":
            properties = payload.get("schema", {}).get("properties", {})
            return (
                "answer.summary"
                if "answer" in properties
                else "ticket.proposed_solution"
                if "ticket" in properties
                else ""
            )
        return ""

    def receive(self, value):
        if value.get("type") == "heartbeat":
            if time.monotonic() - self.last_write >= 10:
                self.flush()
            return
        try:
            frame = Frame.model_validate(value)
        except ValidationError:
            return
        if frame.sequence <= self.sequence:
            return
        self.sequence = frame.sequence
        preview = safe_prefix(frame.preview, self.secrets, lambda text: redact(text, self.secrets))
        self.pending = {
            **frame.model_dump(exclude={"type"}),
            "preview": preview,
            "id": self.id,
            "attempt_id": self.attempt,
            "role": self.role,
            "checkpoint": self.checkpoint,
        }
        if time.monotonic() - self.last_write >= 0.75:
            self.flush()

    def flush(self, *, closed=False, interrupted=False):
        if not self.pending or self.closed:
            return
        try:
            with transaction.atomic():
                job = Job.objects.select_for_update().get(pk=self.job_id)
                if job.status != "RUNNING":
                    return
                if self.execution:
                    if not StepExecution.objects.filter(
                        pk=self.execution, attempt_id=self.attempt, status="RUNNING"
                    ).exists():
                        return
                elif str(job.payload.get("attempt_id")) != self.attempt:
                    return
                phase = {
                    **copy.deepcopy(self.pending),
                    "seen_at": timezone.now().isoformat(),
                    "closed": closed,
                }
                if interrupted:
                    phase["preview"] = ""
                phases = job.progress.get("phases", [])
                phases = (
                    [phase if p["id"] == self.id else p for p in phases]
                    if any(p["id"] == self.id for p in phases)
                    else (phases + [phase])[-16:]
                )
                Job.objects.filter(pk=job.pk).update(progress={"phases": phases})
                self.last_write = time.monotonic()
                self.closed = closed
        except Exception:
            logging.getLogger(__name__).warning("Observed progress could not be saved")


def snapshot(value):
    """Small polling projection; no transcripts, evidence bundles, prompts or credentials."""
    rows = list(
        Job.objects.filter(kind__in=["analysis", "discussion"], target=str(value.pk))
        .order_by("-id")
        .values(
            "id",
            "kind",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "progress",
            "payload__revision",
            "payload__waiting_reason",
            "payload__current_role",
            "payload__next_checkpoint",
            "payload__assignment__connection_id",
            "analysis_run__number",
        )[:50]
    )
    jobs = []
    for row in reversed(rows):
        phases = copy.deepcopy(row["progress"].get("phases", []))
        for phase in phases:
            phase["active"] = (
                row["status"] == "RUNNING" and not phase.get("closed") and phase is phases[-1]
            )
            if not phase["active"]:
                phase["preview"] = ""
            for event in phase.get("events", []):
                if event["state"] == "running" and not phase["active"]:
                    event["state"] = "unknown"
        causes = []
        if row["status"] == "QUEUED" and row["payload__waiting_reason"] == "Waiting for an AI execution slot.":
            causes = ["busy"]
        if (
            not causes
            and
            row["status"] == "QUEUED"
            and row["payload__waiting_reason"]
            and row["payload__assignment__connection_id"]
        ):
            from .providers import public

            connection = AIConnection.objects.filter(
                pk=row["payload__assignment__connection_id"]
            ).first()
            if connection:
                cause = {
                    "QUOTA_EXHAUSTED": "quota",
                    "BUSY": "busy",
                    "MODEL_UNAVAILABLE": "model_unavailable",
                    "AUTH_ERROR": "connection_missing",
                }.get(public(connection)["availability"])
                if cause:
                    causes.append(cause)
        jobs.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "status": row["status"],
                "revision": row["payload__revision"],
                "run_number": row["analysis_run__number"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "waiting_reason": row["payload__waiting_reason"] or "",
                "waiting_causes": causes,
                "phases": phases,
            }
        )
    content = [
        value.status,
        value.error,
        value.updated_at.isoformat(),
        value.messages.aggregate(last=Max("id"))["last"],
        value.versions.aggregate(last=Max("number"))["last"],
        [
            (r["id"], r["status"], r["payload__next_checkpoint"], r["payload__waiting_reason"])
            for r in rows
        ],
    ]
    token = hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest()[:24]
    cursor = hashlib.sha256(
        json.dumps([token, jobs], default=str, sort_keys=True).encode()
    ).hexdigest()[:24]
    return {"progress_token": token, "progress_cursor": cursor, "work_progress": jobs}
