"""Editable conversation drafts, separate from immutable results and publication."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from .discussion_output import message_text
from .models import Job, Request
from .question_actions import source_need
from .sensitive_data import configured_secrets, redact
from .ticket_presentation import publication_blockers


def text(value, maximum, secrets):
    return redact(str(value or ""), secrets)[:maximum]


def result_for(value, number=None):
    versions = value.versions.select_related("request", "run")
    if number is not None:
        return get_object_or_404(versions, number=number)
    return versions.filter(status__in=["READY", "PARTIAL"]).order_by("-number").first()


def verified(version):
    if not version or version.status != "READY" or version.evidence.get("blocking"):
        return False
    claims = version.evidence.get("claims", [])
    if not claims or any(c.get("material", True) and c.get("status") != "supported" for c in claims):
        return False
    if version.request.analysis_protocol in {"2.3", "2.4"}:
        roles = {step.get("public_role") for step in (version.run.steps if version.run else []) if step.get("status") == "DONE"}
        if not {"analyst", "counter_analyst", "verifier"} <= roles:
            return False
    return True


def user_text(message):
    answers = message.data.get("answers")
    return "\n\n".join(item for item in answers.values() if isinstance(item, str)) if isinstance(answers, dict) else message.content


def topic_context(value, topic_id=None):
    """A chosen user turn and its answers; another question is a separate scope."""
    users = value.messages.filter(role="user").exclude(kind__in=["derived_request", "ticket_preparation"])
    topic = get_object_or_404(users, pk=topic_id) if topic_id is not None else users.order_by("-id").first()
    if not topic:
        return None, [], []
    following = users.filter(id__gt=topic.pk).order_by("id").first()
    replies = value.messages.filter(role="assistant", kind="discussion_reply", id__gt=topic.pk).order_by("id")
    runs = value.analysis_runs.filter(started_at__gte=topic.created_at).order_by("-number")
    if following:
        replies = replies.filter(id__lt=following.pk)
        runs = runs.filter(started_at__lt=following.created_at)
    return topic, [message for message in replies if message.data.get("response_status") != "stale" and not message.data.get("ticket_preparation")][-4:], list(runs[:2])


def snapshot(value, draft=None, *, source=None, topic_id=None):
    secrets = configured_secrets()
    def clean(content, maximum):
        return text(content, maximum, secrets)

    draft = draft if draft is not None else value.discussion_state.get("ticket_preparation", {})
    if topic_id is not None and topic_id != draft.get("topic_message_id"):
        draft = {key: item for key, item in draft.items() if key not in {"title", "body", "sources", "generated"}}
    source = source or result_for(value, draft.get("source_version"))
    topic, replies, runs = topic_context(value, topic_id if topic_id is not None else draft.get("topic_message_id"))
    selected_need = clean(user_text(topic) if topic else value.need, 4000)
    latest_run = value.analysis_runs.order_by("-number").first()
    state = "none" if not latest_run else (
        "interrupted" if latest_run.status in {"ERROR", "CANCELLED", "FAILED"}
        else "complete" if latest_run.status == "READY"
        else "partial" if latest_run.status == "PARTIAL"
        else "in_progress"
    )
    scope = clean(source_need(source) if source else value.need, 4000)
    summary = clean((source.explanation.get("response") or source.explanation.get("summary")
                    or source.ticket.get("context") or source.technical_summary) if source else "", 6000)
    inputs = value.messages.filter(role="user").exclude(kind="derived_request")
    if source:
        inputs = inputs.filter(created_at__gt=source.created_at)
    else:
        inputs = inputs.exclude(kind="need")
    changed = inputs.exists()
    checked = verified(source)
    choice = draft.get("scope_choice", "unknown")
    fr = value.language == "fr"
    default_body = ("## Besoin" if fr else "## Need") + "\n\n" + selected_need
    if summary:
        default_body += ("\n\n## Constats de l’analyse" if fr else "\n\n## Analysis findings") + "\n\n" + summary
    if replies:
        default_body += ("\n\n## Constats de la discussion — non vérifiés indépendamment" if fr
                         else "\n\n## Discussion findings — not independently verified")
        default_body += "\n\n" + clean(message_text(replies[-1].content, selected_need), 12000)
    findings = []
    if runs:
        from .conversation import role_reviews

        findings = [claim["statement"] for run in runs for review in role_reviews(run.orchestration) for claim in review["findings"]][:10]
        if findings:
            default_body += ("\n\n## Constats intermédiaires — vérification incomplète\n\n" if fr
                             else "\n\n## Interim findings — incomplete verification\n\n")
            default_body += "\n".join("- " + clean(item, 1000) for item in findings)
    title = clean(draft.get("title") or (source.ticket.get("title") or source.explanation.get("title") if source and (not topic or topic.created_at <= source.created_at) else "")
                  or selected_need.splitlines()[0], 200)
    body = clean(draft.get("body", default_body), 30000)
    note = ("Brouillon : les propositions ajoutées après l’analyse ne sont pas vérifiées."
            if fr else "Draft: proposals added after the analysis have not been independently verified.") if source and checked else (
        "Brouillon non vérifié : les contrôles indépendants sont absents ou incomplets."
        if fr else "Unverified draft: independent checks are missing or incomplete."
    )
    if source and checked and not changed:
        note = ("Brouillon fondé sur une analyse vérifiée ; les modifications du ticket restent à relire."
                if fr else "Draft based on a verified analysis; review any edits to the ticket.")
    reference = ""
    if source:
        reference = f"\n\n[{'Analyse source' if fr else 'Source analysis'} · v{source.number}](/analyses/{value.pk})"
    limitations = [clean(item, 1000) for item in (source.evidence.get("limitations", []) if source else [])[:8]]
    limit_text = (("\n\n## Limites de l’analyse source\n\n" if fr else "\n\n## Source analysis limitations\n\n")
                  + "\n".join("- " + item for item in limitations)) if limitations else ""
    markdown = "# " + title + "\n\n> " + note + "\n\n" + body + limit_text + reference
    generation = Job.objects.filter(kind="discussion", target=str(value.pk), payload__has_key="ticket_preparation").order_by("-id").first()
    topics = [{"id": message.pk, "label": clean(user_text(message), 200)} for message in value.messages.filter(role="user").exclude(kind__in=["derived_request", "ticket_preparation"]).order_by("-id")[:12]]
    if topic and not any(item["id"] == topic.pk for item in topics):
        topics.append({"id": topic.pk, "label": selected_need[:200]})
    return {
        "revision": draft.get("revision", 0),
        "discussion_revision": value.discussion_state.get("revision", 0),
        "source_version": source.number if source else None,
        "source_status": source.status if source else None,
        "source_verified": checked,
        "limitations": limitations,
        "analysis_state": state,
        "verified_scope": scope if source else "",
        "has_new_messages": changed,
        "scope_choice": choice,
        "update_recommended": bool(not checked or choice == "changed" or (changed and choice == "unknown")),
        "title": title,
        "body": body,
        "markdown": markdown,
        "publication_available": bool(source and value.workflow == "request" and source.status in {"READY", "PARTIAL"}),
        "publication_allowed": bool(source and value.workflow == "request" and not publication_blockers(source)),
        "saved_at": draft.get("saved_at"),
        "topic_message_id": topic.pk if topic else None,
        "topics": topics,
        "discussion_findings_available": bool(replies or findings),
        "generation": {"id": generation.pk, "status": generation.status, "error": generation.error,
                       "waiting_reason": generation.payload.get("waiting_reason", "")} if generation else None,
    }


@transaction.atomic
def save(analysis_id, payload):
    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id, deleted_at__isnull=True)
    state = value.discussion_state
    previous = state.get("ticket_preparation", {})
    if previous.get("revision", 0) != payload.expected_revision:
        raise HttpError(409, "The ticket draft changed. Reload it before saving your edits.")
    if state.get("revision", 0) != payload.expected_discussion_revision:
        raise HttpError(409, "The conversation changed. Reload the ticket preparation before saving.")
    source = result_for(value, payload.source_version)
    if payload.source_version is None and source is not None:
        raise HttpError(409, "A new analysis result is available. Reload the ticket preparation.")
    if payload.scope_choice != "unknown" and source is None:
        raise HttpError(422, "An analysis result is required to assess its scope.")
    secrets = configured_secrets()
    topic, _, _ = topic_context(value, payload.topic_message_id or previous.get("topic_message_id"))
    draft = {**{key: previous[key] for key in ("sources", "generated") if key in previous and topic and previous.get("topic_message_id") == topic.pk},
             "revision": previous.get("revision", 0) + 1,
             "discussion_revision": state.get("revision", 0),
             "source_version": source.number if source else None,
             "topic_message_id": topic.pk if topic else None,
             "scope_choice": payload.scope_choice,
             "title": text(payload.title.strip(), 200, secrets), "body": text(payload.body, 30000, secrets),
             "saved_at": timezone.now().isoformat()}
    value.discussion_state = {**state, "ticket_preparation": draft}
    value.save(update_fields=["discussion_state", "updated_at"])
    return snapshot(value, draft, source=source)


@transaction.atomic
def generate(analysis_id, payload, browser_actor):
    """One explicit drafting turn on the selected assistant, never a deep analysis."""
    from .conversation import role_reviews
    from .discussion import MessageIn, enqueue, idle

    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id, deleted_at__isnull=True)
    idle(value)
    draft = value.discussion_state.get("ticket_preparation", {})
    if (draft.get("revision", 0) != payload.expected_revision
            or value.discussion_state.get("revision", 0) != payload.expected_discussion_revision):
        raise HttpError(409, "The conversation or ticket draft changed. Reload before drafting.")
    topic, replies, runs = topic_context(value, payload.topic_message_id)
    if topic is None:
        raise HttpError(422, "Choose a conversation subject before drafting.")
    source = result_for(value, payload.source_version)
    secrets = configured_secrets()
    observations = [{"id": f"message:{m.pk}", "status": "unverified_discussion", "text": text(message_text(m.content, user_text(topic)), 12000, secrets)} for m in replies]
    if draft.get("body"):
        observations.append({"id": f"draft:{draft['revision']}", "status": "unverified_editable_draft", "title": draft["title"], "body": draft["body"]})
    for run in runs:
        for review in role_reviews(run.orchestration):
            if not (review["summary"] or review["findings"]):
                continue
            review["findings"] = review["findings"][:12]
            observations.append({"id": f"run:{run.number}:{review['checkpoint']}", "status": "incomplete_independent_review", "report": review})
    if source:
        observations.append({"id": f"analysis:{source.number}", "status": source.status,
                             "scope": source_need(source), "summary": source.explanation.get("summary") or source.technical_summary,
                             "claims": source.evidence.get("claims", [])[:12], "limits": source.evidence.get("limitations", [])})
    context = redact({"topic": {"id": topic.pk, "question": user_text(topic)}, "observations": observations}, secrets)
    import json
    if len(json.dumps(context)) > 90000:
        raise HttpError(422, "The selected discussion is too large to draft safely. Choose a narrower subject.")
    label = ("Rédiger un ticket sur : " if value.language == "fr" else "Draft a ticket about: ") + user_text(topic)[:1000]
    return enqueue(value.pk, MessageIn(message=label, expected_revision=payload.expected_discussion_revision), browser_actor,
                   preparation={"inputs": context, "expected_draft_revision": payload.expected_revision,
                                "source_version": source.number if source else None, "scope_choice": draft.get("scope_choice", "unknown")})


def complete_generation(value, job, output):
    """Called under the ordinary job/request locks after provider completion."""
    preparation = job.payload["ticket_preparation"]
    allowed = {item["id"] for item in preparation["inputs"]["observations"]}
    if not set(output.sources) <= allowed:
        raise ValueError("The draft cited an unknown conversation source")
    previous = value.discussion_state.get("ticket_preparation", {})
    if previous.get("revision", 0) != preparation["expected_draft_revision"]:
        job.status, job.error, job.finished_at = "ERROR", "The ticket draft changed during generation. Your edits were preserved.", timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        return False
    secrets = configured_secrets()
    draft = {"revision": previous.get("revision", 0) + 1, "discussion_revision": value.discussion_state.get("revision", 0),
             "source_version": preparation["source_version"], "topic_message_id": preparation["inputs"]["topic"]["id"],
             "scope_choice": preparation["scope_choice"], "title": text(output.title, 200, secrets),
             "body": text(output.body, 30000, secrets), "sources": output.sources, "generated": True,
             "saved_at": timezone.now().isoformat()}
    value.discussion_state = {**value.discussion_state, "ticket_preparation": draft}
    value.save(update_fields=["discussion_state"])
    return True
