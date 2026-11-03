"""Session-assisted context preparation for an explicitly requested deep analysis."""

import copy
import re
import unicodedata

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import RequestMessage
from .sensitive_data import configured_secrets, redact

EXCLUDED = {
    "error",
    "decision_revision",
    "ticket_preparation",
    "ticket_publication",
    "analysis_preparation",
    "derived_request",
    "result",
}
ACKNOWLEDGEMENTS = {
    "oui",
    "non",
    "yes",
    "no",
    "ok",
    "okay",
    "exactement",
    "exactly",
    "d accord",
    "agreed",
    "tout a fait",
    "absolument",
    "merci",
    "thanks",
    "bien sur",
    "vas y",
    "go ahead",
}


def normalized(text):
    value = unicodedata.normalize("NFKD", text.lower())
    return " ".join(
        re.findall(r"[a-z0-9]+", "".join(c for c in value if not unicodedata.combining(c)))
    )


def short_reply(text):
    return normalized(text) in ACKNOWLEDGEMENTS


class NeedHint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    need: str = Field(max_length=4000)
    message_ids: list[int] = Field(default_factory=list, max_length=60)


class ContextSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_ids: list[int] = Field(default_factory=list, max_length=60)
    analysis_versions: list[int] = Field(default_factory=list, max_length=6)
    clarification: str = Field(default="", max_length=1000)


def messages(value, cutoff=None):
    rows = value.messages.exclude(kind__in=EXCLUDED)
    if cutoff is not None:
        rows = rows.filter(id__lte=cutoff)
    return rows


def checked_hint(value, hint, cutoff):
    if hint is None or not hint.need.strip() or short_reply(hint.need):
        return None
    ids = hint.message_ids
    references = messages(value, cutoff).filter(pk__in=ids)
    if (
        not ids
        or len(set(ids)) != len(ids)
        or references.count() != len(ids)
        or not references.filter(role="user").exists()
        or references.filter(data__response_status="stale").exists()
    ):
        return None
    return {"need": redact(hint.need.strip(), configured_secrets()), "message_ids": ids}


def suggested_need(value):
    last_user = messages(value).filter(role="user").order_by("-id").first()
    if last_user and value.discussion_state.get("analysis_requested_through") == last_user.pk:
        return value.discussion_state.get("analysis_requested_need", "")
    reply = (
        messages(value).filter(role="assistant", kind="discussion_reply").order_by("-id").first()
    )
    if reply and (not last_user or reply.pk > last_user.pk) and "analysis_context" in reply.data:
        if reply.data.get("response_status") == "stale":
            return ""
        raw = reply.data["analysis_context"]
        try:
            hint = checked_hint(value, NeedHint.model_validate(raw), reply.pk) if raw else None
        except ValidationError:
            hint = None
        return hint["need"] if hint else ""
    # Old records need no regeneration on opening a modal. Keep this fallback
    # conservative: a short reply or an anaphoric follow-up is not a new need.
    if not last_user or short_reply(last_user.content):
        return ""
    text = last_user.content.strip()
    words = normalized(text)
    if len(words.split()) < 4 or re.match(
        r"^(et si|and if|what if|fais le|do it|comme avant|same as before)\b", words
    ):
        return ""
    return redact(text, configured_secrets())[:30000]


def selection_inputs(value, subject, cutoff):
    rows = list(messages(value, cutoff).order_by("-id")[:40])[::-1]
    # The latest native hint can retain older relevant exchanges without a topic
    # catalogue or injecting every old turn into the prompt.
    reply = next(
        (m for m in reversed(rows) if m.role == "assistant" and m.kind == "discussion_reply"), None
    )
    hint_ids = (reply.data.get("analysis_context") or {}).get("message_ids", []) if reply else []
    known = {m.pk for m in rows}
    rows = list(messages(value, cutoff).filter(pk__in=hint_ids).exclude(pk__in=known)[:16]) + rows
    versions = list(value.versions.order_by("-number")[:6])
    from .question_actions import source_need

    return redact(
        {
            "need": subject,
            "exchanges": [
                {
                    "id": m.pk,
                    "role": m.role,
                    "kind": m.kind,
                    "content": m.content[:1800],
                    "is_evidence": False,
                }
                for m in rows
                if m.data.get("response_status") != "stale"
            ],
            "previous_analyses": [
                {
                    "version": v.number,
                    "need": source_need(v)[:1200],
                    "message_ids": v.context_snapshot.get("dossier", {})
                    .get("cycle_scope", {})
                    .get("message_ids", []),
                    "verification_required": True,
                }
                for v in versions
            ],
        },
        configured_secrets(),
    )


def start(value, payload, browser_actor, proposal=None):
    from .discussion import MessageIn, enqueue, pin_environment
    from .environment_context import reject_credentials
    from .orchestration import require_role_coverage
    from .scope_service import assess

    subject = payload.subject.strip() if "subject" in payload.model_fields_set else value.need
    if not subject or short_reply(subject) or "\x00" in subject:
        raise HttpError(422, "Describe the need to investigate.")
    reject_credentials(subject)
    require_role_coverage("2.4")
    if not assess(value, text=subject):
        return value
    cutoff = messages(value).order_by("-id").values_list("id", flat=True).first() or 0
    frozen = pin_environment(value)
    frozen["dossier"]["user_messages"] = []
    frozen["dossier"]["answers"] = []
    value.discussion_state = {
        **value.discussion_state,
        "analysis_requested_need": subject,
        "analysis_requested_through": messages(value)
        .filter(role="user")
        .order_by("-id")
        .values_list("id", flat=True)
        .first(),
    }
    value.save(update_fields=["discussion_state"])
    inputs = selection_inputs(value, subject, cutoff)
    if proposal:
        inputs["ticket_proposal"] = proposal
    return enqueue(
        value.pk,
        MessageIn(message=subject, expected_revision=payload.expected_revision),
        browser_actor,
        analysis_preparation={
            "subject": subject,
            "intent": payload.intent,
            "ticket_proposal": proposal,
            "cutoff": cutoff,
            "snapshot": frozen,
            "answer_offset": len(value.conversation),
            "decision_sequence": value.business_decisions.order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
            or 0,
            "inputs": inputs,
        },
    )


def selected_exchanges(value, ids, cutoff):
    if len(set(ids)) != len(ids):
        raise ValueError("Analysis context repeated a conversation reference")
    rows = list(messages(value, cutoff).filter(pk__in=ids).order_by("id"))
    if len(rows) != len(ids) or any(m.data.get("response_status") == "stale" for m in rows):
        raise ValueError("Analysis context cited an unavailable conversation reference")
    selected = {m.pk: m for m in rows}
    for row in rows:
        if row.role == "user" and short_reply(row.content):
            # An acknowledgement is retained with the exchange it answers,
            # never converted into either a standalone need or technical proof.
            for parent in messages(value, row.pk - 1).order_by("-id")[:4]:
                selected[parent.pk] = parent
                if parent.role == "user" and not short_reply(parent.content):
                    break
    if len(selected) > 100:
        raise ValueError("Analysis context contains too many conversation references")
    result = []
    for row in sorted(selected.values(), key=lambda item: item.pk):
        if row.data.get("response_status") == "stale":
            continue
        classification = (
            "assistant_question_or_hypothesis"
            if row.role == "assistant"
            else "contextual_confirmation"
            if short_reply(row.content)
            else "user_clarification"
            if row.kind in {"answer", "answers", "clarification"}
            else "user_statement"
        )
        result.append(
            {
                "id": row.pk,
                "role": row.role,
                "kind": row.kind,
                "content": row.content,
                "classification": classification,
                "is_technical_evidence": False,
            }
        )
    return redact(result, configured_secrets())


def complete(value, job, output):
    from .discussion import launch_deep_analysis

    prep = job.payload["analysis_preparation"]
    exchanges = selected_exchanges(value, output.message_ids, prep["cutoff"])
    if output.clarification:
        RequestMessage.objects.create(
            request=value,
            role="assistant",
            kind="discussion_reply",
            content=redact(output.clarification, configured_secrets()),
            data={
                "analysis_context": {
                    "need": prep["subject"],
                    "message_ids": [m["id"] for m in exchanges],
                },
                "analysis_context_clarification": True,
            },
        )
        value.status, value.error = "DISCUSSING", ""
        value.save(update_fields=["status", "error", "updated_at"])
        job.status, job.finished_at = "DONE", timezone.now()
        job.save(update_fields=["status", "finished_at"])
        return
    references = []
    if len(set(output.analysis_versions)) != len(output.analysis_versions):
        raise ValueError("Analysis context repeated a result reference")
    for number in output.analysis_versions:
        version = get_object_or_404(value.versions, number=number, created_at__lte=job.created_at)
        references.append(
            {
                "id": str(version.pk),
                "version": version.number,
                "baseline": version.baseline,
                "verification_required": True,
            }
        )
    users = [m for m in exchanges if m["role"] == "user"]
    scope = {
        "subject": prep["subject"],
        "topic_message_id": next(
            (m["id"] for m in reversed(users) if not short_reply(m["content"])), None
        ),
        "message_ids": [m["id"] for m in users],
        "context_exchanges": exchanges,
        "analysis_references": references,
        "answer_offset": prep["answer_offset"],
        "decision_sequence": prep["decision_sequence"],
        "preparation_job_id": job.pk,
    }
    job.status, job.finished_at = "DONE", timezone.now()
    job.save(update_fields=["status", "finished_at"])
    launch_deep_analysis(
        value,
        prep["intent"],
        scope,
        prep.get("ticket_proposal"),
        frozen=copy.deepcopy(job.payload["snapshot"]),
    )
    run = value.analysis_runs.filter(job__payload__cycle_scope__preparation_job_id=job.pk).first()
    if run:
        job.payload["analysis_run_id"] = str(run.pk)
        job.save(update_fields=["payload"])


INSTRUCTIONS = (
    "Prepare context for the user's explicitly requested independent deep analysis. This is context selection, "
    "not the analysis itself. Keep need exactly as submitted; never invent or rewrite a requirement. "
    "Use your persistent conversation context and supplied exchanges to choose a small set of relevant actual message IDs. "
    "A later unrelated question must not replace the need. Do not select merely by recency. "
    "A yes/no acknowledgement has meaning only with the question/proposal it answers; include that exchange. "
    "Previous assistant statements are hypotheses, never independent evidence or normative business decisions. "
    "Select earlier analysis versions only when relevant, as references requiring renewed source checks. "
    "If an essential fact is missing after compaction or unavailable history, return one short clarification "
    "instead of fabricating context. An empty message_ids list is valid if the explicit need is self-contained. "
    "Do not inspect code, query a database, generate a ticket, publish, or perform the three-role analysis now. "
    "Never output findings or private reasoning. Return only message_ids, analysis_versions and clarification."
)
