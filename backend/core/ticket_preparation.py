"""Editable conversation drafts, separate from immutable results and publication."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from .discussion_output import message_text
from .models import ConversationTicket, Job, Request, RequestMessage
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


def version_workflow(version):
    # The frozen dossier records launch inputs; automatic intent may be resolved
    # afterwards. Consolidated output belongs to this result, never today's request.
    if version.explanation:
        return "question"
    if version.ticket:
        return "request"
    if version.run_id:
        resolved = version.run.orchestration.get("intent_resolution", {}).get("workflow")
        if resolved:
            return resolved
    return version.context_snapshot.get("dossier", {}).get("workflow", version.request.workflow)


def publication_ticket(version, identifier):
    if not identifier:
        return None
    return get_object_or_404(ConversationTicket, pk=identifier, request_id=version.request_id, source_version=version)


def selected(value, ticket_id=None, *, new=False):
    if new:
        return None, {}
    identifier = ticket_id or value.discussion_state.get("ticket_preparation_id")
    if identifier:
        ticket = get_object_or_404(ConversationTicket, pk=identifier, request=value)
        return ticket, ticket.draft.copy()
    return None, value.discussion_state.get("ticket_preparation", {}).copy()


def store(value, draft, ticket=None):
    source = result_for(value, draft["source_version"]) if draft.get("source_version") else None
    topic = value.messages.filter(pk=draft.get("topic_message_id"), role="user").first()
    if ticket is None:
        ticket = ConversationTicket.objects.create(request=value, source_version=source, topic_message=topic, draft=draft)
        RequestMessage.objects.create(request=value, role="assistant", kind="ticket_preparation",
            content=draft["title"], data={"conversation_ticket_id":str(ticket.pk)}, version=source)
    else:
        ticket.source_version, ticket.topic_message, ticket.draft = source, topic, draft
        ticket.save(update_fields=["source_version", "topic_message", "draft", "updated_at"])
    # Keep the former selected-draft shape readable by stored jobs and older clients.
    value.discussion_state = {**value.discussion_state, "ticket_preparation":draft, "ticket_preparation_id":str(ticket.pk)}
    value.save(update_fields=["discussion_state", "updated_at"])
    return ticket


def summaries(value):
    rows = []
    for ticket in value.conversation_tickets.select_related("source_version").prefetch_related("publications").order_by("created_at", "id"):
        publications = list(ticket.publications.all())
        state = "PUBLISHED" if any(p.status == "PUBLISHED" for p in publications) else "ERROR" if any(p.status in {"ERROR", "UNCERTAIN"} for p in publications) else "PUBLISHING" if any(p.status == "PUBLISHING" for p in publications) else "DRAFT"
        rows.append({"id":str(ticket.pk), "title":ticket.draft.get("title", ""), "source_version":ticket.source_version.number if ticket.source_version_id else None,
                     "topic_message_id":ticket.topic_message_id, "revision":ticket.draft.get("revision", 0), "status":state,
                     "created_at":ticket.created_at, "updated_at":ticket.updated_at})
    return rows


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


def snapshot(value, draft=None, *, source=None, topic_id=None, source_number=None, ticket_id=None, new=False, without_analysis=False):
    secrets = configured_secrets()
    def clean(content, maximum):
        return text(content, maximum, secrets)

    ticket, saved = selected(value, ticket_id, new=new)
    draft = draft if draft is not None else saved
    if source_number is not None and source_number != draft.get("source_version"):
        draft = {key:item for key,item in draft.items() if key != "topic_message_id"}
    if source_number is not None and source_number != draft.get("source_version") or without_analysis:
        draft = {key:item for key,item in draft.items() if key not in {"title", "body", "sources", "generated", "source_version"}}
    if topic_id is not None and topic_id != draft.get("topic_message_id"):
        draft = {key: item for key, item in draft.items() if key not in {"title", "body", "sources", "generated"}}
    if source is None and not without_analysis:
        if source_number is not None:
            source = result_for(value, source_number)
            if topic_id is None and not draft.get("topic_message_id"):
                topic_id = source.context_snapshot.get("dossier", {}).get("cycle_scope", {}).get("topic_message_id")
                if topic_id is None:
                    topic_id = value.messages.filter(role="user", created_at__lte=source.created_at).exclude(
                        kind__in=["ticket_preparation", "derived_request"]
                    ).order_by("-id").values_list("id", flat=True).first()
        elif "source_version" in draft:
            source = result_for(value, draft["source_version"]) if draft["source_version"] else None
        elif value.versions.count() == 1:
            candidate = result_for(value)
            scope_ids = candidate.context_snapshot.get("dossier", {}).get("cycle_scope", {}).get("message_ids") if candidate else None
            latest_topic = topic_id or draft.get("topic_message_id") or value.messages.filter(role="user").exclude(kind__in=["ticket_preparation", "derived_request"]).order_by("-id").values_list("id", flat=True).first()
            if scope_ids is None or latest_topic in scope_ids:
                source = candidate
    topic, replies, runs = topic_context(value, topic_id if topic_id is not None else draft.get("topic_message_id"))
    selected_need = clean(user_text(topic) if topic else value.need, 4000)
    latest_run = source.run if source and source.run_id else runs[0] if runs else None
    state = "none" if not latest_run else (
        "interrupted" if latest_run.status in {"ERROR", "CANCELLED", "FAILED"}
        else "complete" if latest_run.status == "READY"
        else "partial" if latest_run.status == "PARTIAL"
        else "in_progress"
    )
    scope = clean(source_need(source) if source else value.need, 4000)
    summary = clean((source.explanation.get("response") or source.explanation.get("summary")
                    or source.ticket.get("context") or source.technical_summary) if source else "", 6000)
    changed = bool(topic and source and topic.created_at > source.created_at)
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
        reference = f"\n\n[{'Analyse source' if fr else 'Source analysis'} · v{source.number}](/analyses/{value.pk}?version={source.number})"
    limitations = [clean(item, 1000) for item in (source.evidence.get("limitations", []) if source else [])[:8]]
    limit_text = (("\n\n## Limites de l’analyse source\n\n" if fr else "\n\n## Source analysis limitations\n\n")
                  + "\n".join("- " + item for item in limitations)) if limitations else ""
    markdown = "# " + title + "\n\n> " + note + "\n\n" + body + limit_text + reference
    generation = Job.objects.filter(kind="discussion", target=str(value.pk), payload__has_key="ticket_preparation")
    if ticket:
        generation = generation.filter(payload__ticket_preparation__conversation_ticket_id=str(ticket.pk))
    elif new:
        generation = generation.none()
    generation = generation.order_by("-id").first()
    topics = [{"id": message.pk, "label": clean(user_text(message), 200)} for message in value.messages.filter(role="user").exclude(kind__in=["derived_request", "ticket_preparation"]).order_by("-id")[:12]]
    if topic and not any(item["id"] == topic.pk for item in topics):
        topics.append({"id": topic.pk, "label": selected_need[:200]})
    return {
        "id": str(ticket.pk) if ticket else None,
        "read_only": bool(ticket and ticket.publications.exclude(status="ERROR").exists()),
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
        "publication_available": bool(source and version_workflow(source) == "request" and source.status in {"READY", "PARTIAL"}),
        "publication_allowed": bool(source and version_workflow(source) == "request" and not publication_blockers(source)),
        "saved_at": draft.get("saved_at"),
        "topic_message_id": topic.pk if topic else None,
        "topics": topics,
        "analyses": [{"number":v.number, "status":v.status, "subject":clean(source_need(v), 200), "topic_message_id":v.context_snapshot.get("dossier", {}).get("cycle_scope", {}).get("topic_message_id")} for v in value.versions.select_related("request").order_by("-number")],
        "needs_source_choice": source is None and value.versions.exists(),
        "discussion_findings_available": bool(replies or findings),
        "generation": {"id": generation.pk, "status": generation.status, "error": generation.error,
                       "waiting_reason": generation.payload.get("waiting_reason", "")} if generation else None,
    }


@transaction.atomic
def save(analysis_id, payload):
    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id, deleted_at__isnull=True)
    state = value.discussion_state
    ticket, previous = selected(value, getattr(payload, "ticket_id", None), new=getattr(payload, "new_ticket", False))
    if previous.get("revision", 0) != payload.expected_revision:
        raise HttpError(409, "The ticket draft changed. Reload it before saving your edits.")
    if state.get("revision", 0) != payload.expected_discussion_revision:
        raise HttpError(409, "The conversation changed. Reload the ticket preparation before saving.")
    source = result_for(value, payload.source_version) if payload.source_version else None
    if ticket and ticket.publications.exclude(status="ERROR").exists():
        raise HttpError(409, "This ticket already has a publication. Prepare another ticket to change its subject.")
    if payload.scope_choice != "unknown" and source is None:
        raise HttpError(422, "An analysis result is required to assess its scope.")
    secrets = configured_secrets()
    topic, _, _ = topic_context(value, payload.topic_message_id or previous.get("topic_message_id"))
    if ticket and ticket.publications.exists() and (ticket.source_version_id != (source.pk if source else None)
            or ticket.topic_message_id != (topic.pk if topic else None)):
        raise HttpError(409, "This ticket already has a publication. Prepare another ticket to change its subject.")
    draft = {**{key: previous[key] for key in ("sources", "generated") if key in previous and topic and previous.get("topic_message_id") == topic.pk and previous.get("source_version") == payload.source_version},
             "revision": previous.get("revision", 0) + 1,
             "discussion_revision": state.get("revision", 0),
             "source_version": source.number if source else None,
             "topic_message_id": topic.pk if topic else None,
             "scope_choice": payload.scope_choice,
             "title": text(payload.title.strip(), 200, secrets), "body": text(payload.body, 30000, secrets),
             "saved_at": timezone.now().isoformat()}
    ticket = store(value, draft, ticket)
    return snapshot(value, draft, source=source, ticket_id=ticket.pk)


@transaction.atomic
def generate(analysis_id, payload, browser_actor):
    """One explicit drafting turn on the selected assistant, never a deep analysis."""
    from .conversation import role_reviews
    from .discussion import MessageIn, enqueue, idle

    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id, deleted_at__isnull=True)
    idle(value)
    ticket, draft = selected(value, getattr(payload, "ticket_id", None))
    if (draft.get("revision", 0) != payload.expected_revision
            or value.discussion_state.get("revision", 0) != payload.expected_discussion_revision):
        raise HttpError(409, "The conversation or ticket draft changed. Reload before drafting.")
    topic, replies, runs = topic_context(value, payload.topic_message_id)
    if topic is None:
        raise HttpError(422, "Choose a conversation subject before drafting.")
    source = result_for(value, payload.source_version) if payload.source_version else None
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
                                "conversation_ticket_id":str(ticket.pk) if ticket else None,
                                "source_version": source.number if source else None, "scope_choice": draft.get("scope_choice", "unknown")})


def complete_generation(value, job, output):
    """Called under the ordinary job/request locks after provider completion."""
    preparation = job.payload["ticket_preparation"]
    allowed = {item["id"] for item in preparation["inputs"]["observations"]}
    if not set(output.sources) <= allowed:
        raise ValueError("The draft cited an unknown conversation source")
    ticket, previous = selected(value, preparation.get("conversation_ticket_id"))
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
    store(value, draft, ticket)
    return True
