"""Editable conversation drafts, separate from immutable results and publication."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from .models import ConversationTicket, Job, Request, RequestMessage, ResultVersion
from .question_actions import source_need
from .sensitive_data import configured_secrets, redact


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
    return get_object_or_404(ConversationTicket, pk=identifier, request_id=version.request_id, source_version_id=version.pk)


def publication_source(request_id, number=None, ticket_id=None):
    if ticket_id:
        ticket = get_object_or_404(ConversationTicket.objects.select_related("request__environment", "source_version"), pk=ticket_id, request_id=request_id, request__deleted_at__isnull=True)
        if number is not None and (not ticket.source_version_id or ticket.source_version.number != number):
            raise HttpError(404, "This ticket does not belong to the selected result.")
        if ticket.source_version_id:
            return ticket.source_version
        # Presentation only: never persisted or exposed as an analysis/result/evidence.
        return ResultVersion(id=None, request=ticket.request, number=0, status="DRAFT",
            language=ticket.request.language, environment_name=ticket.request.environment_name_snapshot or (ticket.request.environment.name if ticket.request.environment_id else ""),
            ticket={"title":ticket.draft.get("title", ""), "need":ticket.draft.get("body", "")},
            baseline=[], context_snapshot={}, evidence={})
    return get_object_or_404(ResultVersion,request_id=request_id,number=number,request__deleted_at__isnull=True)


def publication_requires_ack(ticket, content=None, version=None, presentation=None):
    if not verified(ticket.source_version) or version_workflow(ticket.source_version) != "request" or ticket.draft.get("generated") or ticket.draft.get("user_edited"):
        return True
    anchor = ticket.request.messages.filter(pk=ticket.draft.get("anchor_message_id") or ticket.topic_message_id).first()
    if bool(anchor and anchor.created_at > ticket.source_version.created_at) or ticket.draft.get("scope_choice") == "changed":
        return True
    if content is not None:
        if not presentation or presentation.get("ticket_format") != "standard":
            return True
        from .ticket_presentation import detailed_sections
        prepared = snapshot(ticket.request,ticket_id=ticket.pk)
        extra = detailed_sections(version or ticket.source_version,presentation)
        return content.get("title") != prepared["title"] or content.get("body") != prepared["markdown"] + ("\n\n"+extra if extra else "")
    return False


def active_ticket(value):
    return value.conversation_tickets.filter(active=True).select_related("source_version").first()


def selected(value, ticket_id=None, *, new=False):
    # The compatibility pointer is retained for old jobs, never used to select a
    # published or superseded document as today's editable draft.
    ticket = (get_object_or_404(ConversationTicket, pk=ticket_id, request=value)
              if ticket_id else active_ticket(value))
    return (ticket, ticket.draft.copy()) if ticket else (None, {})


@transaction.atomic
def store(value, draft, ticket=None):
    Request.objects.select_for_update().get(pk=value.pk)
    source = result_for(value, draft["source_version"]) if draft.get("source_version") else None
    topic = value.messages.filter(pk=draft.get("topic_message_id"), role="user").first()
    if ticket is None:
        if active_ticket(value):
            raise HttpError(409, "A ticket draft already exists. Resume it or explicitly confirm its replacement.")
        ticket = ConversationTicket.objects.create(request=value, source_version=source, topic_message=topic, draft=draft)
    else:
        if not ticket.active:
            raise HttpError(409, "This ticket is no longer the active draft.")
        ticket.source_version, ticket.topic_message, ticket.draft = source, topic, draft
        ticket.save(update_fields=["source_version", "topic_message", "draft", "updated_at"])
    value.discussion_state = {**value.discussion_state, "ticket_preparation":draft, "ticket_preparation_id":str(ticket.pk)}
    value.save(update_fields=["discussion_state", "updated_at"])
    return ticket


def publication_state(publications):
    occupied = {item.destination for item in publications if item.status != "ERROR"}
    unresolved = [item for item in publications if item.status != "ERROR" or item.destination not in occupied]
    return next((status for status in ["UNCERTAIN", "PUBLISHING", "ERROR", "PUBLISHED"]
                 if any(item.observed_status == status for item in unresolved)), "DRAFT")


def summaries(value):
    rows = []
    for ticket in value.conversation_tickets.select_related("source_version").prefetch_related("publications").order_by("created_at", "id"):
        publications = list(ticket.publications.all())
        state = publication_state(publications)
        rows.append({"id":str(ticket.pk), "title":ticket.draft.get("title", ""), "source_version":ticket.source_version.number if ticket.source_version_id else None,
                     "active":ticket.active, "topic_message_id":ticket.topic_message_id, "revision":ticket.draft.get("revision", 0), "status":state,
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


def anchor_context(value, anchor_id):
    anchor = get_object_or_404(value.messages.exclude(kind__in=["error", "decision_revision", "ticket_preparation"]), pk=anchor_id)
    if anchor.data.get("response_status") == "stale":
        raise HttpError(409, "This response was superseded. Choose a current response.")
    topic = value.messages.filter(role="user", id__lte=anchor.pk).exclude(kind__in=["answer", "answers", "ticket_preparation", "derived_request"]).order_by("-id").first()
    if topic is None:
        topic = value.messages.filter(role="user", id__lte=anchor.pk).order_by("-id").first()
    rows = list(value.messages.filter(id__gte=topic.pk if topic else anchor.pk, id__lte=anchor.pk).exclude(kind__in=["error", "decision_revision", "ticket_preparation"]).order_by("-id")[:20])[::-1]
    return anchor, topic, [row for row in rows if row.data.get("response_status") != "stale"]


def snapshot(value, draft=None, *, source=None, topic_id=None, source_number=None, ticket_id=None, new=False, without_analysis=False, anchor_id=None):
    secrets = configured_secrets()
    def clean(content, maximum):
        return text(content, maximum, secrets)

    ticket, saved = selected(value, ticket_id, new=new)
    draft = draft if draft is not None else saved
    anchor_id = anchor_id or draft.get("anchor_message_id")
    anchor, scoped_rows = None, []
    if anchor_id:
        anchor, anchor_topic, scoped_rows = anchor_context(value, anchor_id)
        topic_id = anchor_topic.pk if anchor_topic else None
        if anchor.version_id and source_number is None:
            source_number = anchor.version.number
        elif source_number is None and "source_version" not in draft:
            candidates = [candidate for candidate in value.versions.select_related("request", "run").order_by("-number")
                if anchor.pk in candidate.context_snapshot.get("dossier", {}).get("cycle_scope", {}).get("message_ids", [])]
            if len(candidates) == 1:
                source_number = candidates[0].number
            else:
                without_analysis = True
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
    scope_topic = topic_id if topic_id is not None else draft.get("topic_message_id")
    topic, replies, runs = topic_context(value, scope_topic) if scope_topic is not None or not ticket else (None, [], [])
    if scoped_rows:
        replies = [message for message in scoped_rows if message.role == "assistant" and message.kind == "discussion_reply" and not message.data.get("ticket_preparation")]
        runs = [run for run in runs if not anchor or run.started_at <= anchor.created_at]
    selected_need = clean(user_text(topic) if topic else value.need, 4000)
    latest_run = source.run if source and source.run_id else runs[0] if runs else None
    state = "none" if not latest_run else (
        "interrupted" if latest_run.status in {"ERROR", "CANCELLED", "FAILED"}
        else "complete" if latest_run.status == "READY"
        else "partial" if latest_run.status == "PARTIAL"
        else "in_progress"
    )
    scope = clean(source_need(source) if source else value.need, 4000)
    changed = bool(topic and source and topic.created_at > source.created_at)
    checked = verified(source)
    choice = draft.get("scope_choice", "unknown")
    fr = value.language == "fr"
    default_body = ("## Besoin" if fr else "## Need") + "\n\n" + selected_need
    findings = []
    if runs:
        from .conversation import role_reviews
        findings = [claim["statement"] for run in runs for review in role_reviews(run.orchestration) for claim in review["findings"]][:10]
    if source and source.ticket:
        expected = source.ticket.get("expected_behavior") or source.ticket.get("business_need")
        criteria = source.ticket.get("acceptance_criteria")
        if expected:
            default_body += ("\n\n## Comportement attendu\n\n" if fr else "\n\n## Expected behavior\n\n") + clean("\n".join(expected) if isinstance(expected,list) else expected, 1800)
        if criteria:
            default_body += ("\n\n## Critères d’acceptation\n\n" if fr else "\n\n## Acceptance criteria\n\n") + "\n".join("- "+clean(item,500) for item in criteria[:8])
    title = clean(draft.get("title") or (source.ticket.get("title") or source.explanation.get("title") if source and (not topic or topic.created_at <= source.created_at) else "")
                  or selected_need.splitlines()[0], 200)
    body = clean(draft.get("body", default_body), 30000)
    limitations = [clean(item, 1000) for item in (source.evidence.get("limitations", []) if source else [])[:8]]
    # Keep provenance and verification in metadata, without duplicating the title
    # or inserting the full analysis warnings into the external description.
    markdown = body
    ticket_verified = checked and version_workflow(source) == "request" and not (changed or draft.get("generated") or draft.get("user_edited") or choice == "changed")
    generation = Job.objects.filter(kind="discussion", target=str(value.pk), payload__has_key="ticket_preparation")
    if ticket:
        generation = generation.filter(payload__ticket_preparation__conversation_ticket_id=str(ticket.pk))
    elif new:
        generation = generation.none()
    generation = generation.order_by("-id").first()
    return {
        "id": str(ticket.pk) if ticket else None,
        "read_only": bool(ticket and (not ticket.active or ticket.publications.exclude(status="ERROR").exists())),
        "active": bool(ticket and ticket.active),
        "can_recover_publication": bool(ticket and ticket.publications.filter(status__in=["PUBLISHING", "UNCERTAIN"]).exists()),
        "proposal": draft.get("proposal"),
        "unchanged": draft.get("unchanged", False),
        "initial_pending": bool(ticket and not ticket.draft.get("body")),
        "revision": draft.get("revision", 0),
        "discussion_revision": value.discussion_state.get("revision", 0),
        "source_version": source.number if source else None,
        "source_status": source.status if source else None,
        "source_verified": checked,
        "ticket_verified": bool(ticket_verified),
        "limitations": limitations,
        "analysis_state": state,
        "verified_scope": scope if source else "",
        "has_new_messages": changed,
        "scope_choice": choice,
        "update_recommended": bool(not checked or choice == "changed" or (changed and choice == "unknown")),
        "title": title,
        "body": body,
        "markdown": markdown,
        "publication_available": True,
        "publication_allowed": True,
        "saved_at": draft.get("saved_at"),
        "topic_message_id": topic.pk if topic else None,
        "topics": [],
        "anchor_message_id": anchor_id,
        "context_message_ids": [message.pk for message in scoped_rows] or draft.get("context_message_ids", []),
        "analyses": [{"number":v.number, "status":v.status, "subject":clean(source_need(v), 200), "topic_message_id":v.context_snapshot.get("dossier", {}).get("cycle_scope", {}).get("topic_message_id")} for v in value.versions.select_related("request").order_by("-number")],
        "needs_source_choice": source is None and value.versions.exists(),
        "discussion_findings_available": bool(replies or findings),
        "clarification": generation.payload.get("ticket_preparation", {}).get("clarification", "") if generation else "",
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
    if ticket and (not ticket.active or ticket.publications.exclude(status="ERROR").exists()):
        raise HttpError(409, "This ticket already has a publication. Prepare another ticket to change its subject.")
    if payload.scope_choice != "unknown" and source is None:
        raise HttpError(422, "An analysis result is required to assess its scope.")
    secrets = configured_secrets()
    if ticket and payload.topic_message_id is None and not previous.get("topic_message_id"):
        topic = None
    else:
        topic, _, _ = topic_context(value, payload.topic_message_id or previous.get("topic_message_id"))
    if ticket and ticket.publications.exists() and (ticket.source_version_id != (source.pk if source else None)
            or ticket.topic_message_id != (topic.pk if topic else None)):
        raise HttpError(409, "This ticket already has a publication. Prepare another ticket to change its subject.")
    draft = {**{key: previous[key] for key in ("sources", "generated", "context_message_ids", "prepared_through_message_id", "requested_by_message_id") if key in previous},
             "revision": previous.get("revision", 0) + 1,
             "discussion_revision": state.get("revision", 0),
             "source_version": source.number if source else None,
             "topic_message_id": topic.pk if topic else None,
             "scope_choice": payload.scope_choice,
             "anchor_message_id": getattr(payload,"anchor_message_id",None) or previous.get("anchor_message_id"),
             "user_edited": bool(previous.get("user_edited") or previous.get("revision",0) and (payload.title != previous.get("title") or payload.body != previous.get("body"))),
             "title": text(payload.title.strip(), 200, secrets), "body": text(payload.body, 30000, secrets),
             "saved_at": timezone.now().isoformat()}
    if source and not previous.get("revision"):
        initial = snapshot(value,new=True,source_number=source.number,topic_id=topic.pk if topic else None,anchor_id=draft.get("anchor_message_id"))
        draft["user_edited"] = payload.title != initial["title"] or payload.body != initial["body"]
    if not draft.get("anchor_message_id") and topic:
        _, replies, _ = topic_context(value,topic.pk)
        draft["anchor_message_id"] = replies[-1].pk if replies else topic.pk
    if draft.get("anchor_message_id"):
        anchor, topic, rows = anchor_context(value, draft["anchor_message_id"])
        draft["topic_message_id"] = topic.pk if topic else None
        draft["context_message_ids"] = [message.pk for message in rows]
    ticket = store(value, draft, ticket)
    return snapshot(value, draft, source=source, ticket_id=ticket.pk)


def assert_editable(ticket):
    if not ticket.active or ticket.publications.exclude(status="ERROR").exists():
        raise HttpError(409, "Verify the existing publication before changing this draft.")


def source_from_output(value, output, allowed):
    number = getattr(output, "source_version", None)
    if number is not None:
        if f"analysis:{number}" not in allowed or f"analysis:{number}" not in output.sources:
            raise ValueError("The proposed source analysis was not consulted")
        return result_for(value, number)
    return None


@transaction.atomic
def generate(analysis_id, payload, browser_actor):
    """One session-native drafting turn, with no subject selection or deep cycle."""
    from .discussion import MessageIn, enqueue, idle

    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id, deleted_at__isnull=True)
    ticket = active_ticket(value)
    purpose = getattr(payload, "purpose", "refresh")
    running = Job.objects.filter(kind="discussion", target=str(value.pk), status__in=["QUEUED", "RUNNING"],
                                 payload__ticket_preparation__conversation_ticket_id=str(ticket.pk) if ticket else "").first()
    if running and purpose == "prepare":
        return value
    idle(value)
    if payload.expected_discussion_revision != value.discussion_state.get("revision", 0):
        raise HttpError(409, "The conversation changed. Reload the ticket preparation before saving.")
    if ticket:
        if payload.ticket_id and str(ticket.pk) != str(payload.ticket_id):
            raise HttpError(409, "The active ticket draft changed. Reopen it before continuing.")
        if payload.expected_revision != ticket.draft.get("revision", 0):
            raise HttpError(409, "The ticket draft changed. Reload it before saving your edits.")
        assert_editable(ticket)
        if purpose == "prepare" and ticket.draft.get("body"):
            return value
    elif payload.ticket_id or payload.expected_revision:
        raise HttpError(409, "The active ticket draft changed. Reopen it before continuing.")
    if purpose == "replace" and (not ticket or not payload.replace_confirmed):
        raise HttpError(409, "Confirm replacement of the existing ticket draft.")
    if ticket is None:
        ticket = store(value, {"revision":1, "title":"", "body":"", "source_version":None,
                               "scope_choice":"unknown", "context_message_ids":[]})
        purpose = "prepare"
    draft = ticket.draft
    messages = list(value.messages.exclude(kind__in=["ticket_preparation", "ticket_publication", "error", "decision_revision"])
                    .order_by("-id")[:24])[::-1]
    messages = [message for message in messages if message.data.get("response_status") != "stale" and not message.data.get("ticket_preparation")]
    secrets = configured_secrets()
    observations = [{"id":f"message:{m.pk}", "role":m.role, "status":"unverified_discussion", "text":text(user_text(m), 3500, secrets)} for m in messages]
    versions = list(value.versions.select_related("request", "run").order_by("-number")[:6])
    if ticket.source_version_id and all(v.pk != ticket.source_version_id for v in versions):
        versions.append(ticket.source_version)
    for version in versions:
        observations.append({"id":f"analysis:{version.number}", "status":version.status, "scope":source_need(version),
                             "summary":version.explanation.get("summary") or version.technical_summary,
                             "claims":version.evidence.get("claims", [])[:12], "limits":version.evidence.get("limitations", [])})
    from .conversation import role_reviews
    for run in value.analysis_runs.order_by("-number")[:3]:
        if any(version.run_id == run.pk for version in versions):
            continue
        for review in role_reviews(run.orchestration):
            if review["summary"] or review["findings"]:
                review["findings"] = review["findings"][:12]
                observations.append({"id":f"run:{run.number}:{review['checkpoint']}", "status":"incomplete_independent_review", "report":review})
    inputs = redact({"operation":purpose, "current_draft":({"title":draft.get("title", ""), "body":draft.get("body", "")} if purpose != "replace" else None),
                     "previous_draft_title":draft.get("title", ""), "last_prepared_message_id":draft.get("prepared_through_message_id"),
                     "focus_message_id":getattr(payload, "anchor_message_id", None), "observations":observations}, secrets)
    if inputs["focus_message_id"]:
        get_object_or_404(value.messages, pk=inputs["focus_message_id"])
    label = "Actualiser le brouillon du ticket" if purpose == "refresh" and value.language == "fr" else "Préparer un ticket pour le besoin courant" if value.language == "fr" else "Refresh the ticket draft" if purpose == "refresh" else "Prepare a ticket for the current need"
    return enqueue(value.pk, MessageIn(message=label, expected_revision=payload.expected_discussion_revision), browser_actor,
                   preparation={"inputs":inputs, "purpose":purpose, "expected_draft_revision":draft["revision"],
                                "conversation_ticket_id":str(ticket.pk), "source_version":draft.get("source_version"),
                                "scope_choice":draft.get("scope_choice", "unknown"), "context_message_ids":[m.pk for m in messages],
                                "prepared_through_message_id":messages[-1].pk if messages else None})


def complete_generation(value, job, output):
    """The initial proposal is saved; later proposals await an explicit human choice."""
    import uuid
    preparation = job.payload["ticket_preparation"]
    allowed = {item["id"] for item in preparation["inputs"]["observations"]}
    if not set(output.sources) <= allowed:
        raise ValueError("The draft cited an unknown conversation source")
    ticket, previous = selected(value, preparation.get("conversation_ticket_id"))
    if (not ticket or not ticket.active or previous.get("revision", 0) != preparation["expected_draft_revision"]
            or ticket.publications.exclude(status="ERROR").exists()):
        job.status, job.error, job.finished_at = "ERROR", "The ticket draft changed during generation. Your edits were preserved.", timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        return False
    clarification = getattr(output, "clarification", "")
    if clarification:
        question = text(clarification, 1000, configured_secrets())
        RequestMessage.objects.create(request=value, role="assistant", kind="discussion_reply", content=question, data={"ticket_clarification":True})
        value.discussion_state = {**value.discussion_state, "pending_ticket_clarification":{"message_ids":preparation.get("context_message_ids", []), "ticket_id":str(ticket.pk)}}
        value.save(update_fields=["discussion_state", "updated_at"])
        job.payload["ticket_preparation"]["clarification"] = question
    elif getattr(output, "unchanged", False) or (output.title == previous.get("title") and output.body == previous.get("body")):
        if not previous.get("body"):
            raise ValueError("An initial ticket requires content or a clarification question")
        store(value, {**previous, "unchanged":True, "proposal":None}, ticket)
    else:
        source = source_from_output(value, output, allowed)
        candidate = {"id":str(uuid.uuid4()), "title":text(output.title.strip(), 200, configured_secrets()),
                     "body":text(output.body, 30000, configured_secrets()), "sources":output.sources,
                     "source_version":source.number if source else None, "generated":True,
                     "context_message_ids":preparation.get("context_message_ids", []),
                     "prepared_through_message_id":preparation.get("prepared_through_message_id"),
                     "base_revision":previous["revision"], "replacement":preparation.get("purpose") == "replace"}
        if not previous.get("body") or candidate["replacement"]:
            # Replacement was explicitly authorized with this exact base revision.
            if candidate["replacement"]:
                ticket.active = False
                ticket.save(update_fields=["active", "updated_at"])
                ticket = None
            draft = {**candidate, "revision":previous["revision"]+1, "scope_choice":"unknown", "saved_at":timezone.now().isoformat()}
            draft.pop("id")
            store(value, draft, ticket)
        else:
            store(value, {**previous, "proposal":candidate, "unchanged":False}, ticket)
    job.status, job.finished_at = "DONE", timezone.now()
    job.save(update_fields=["payload", "status", "finished_at"])
    return not bool(clarification)


@transaction.atomic
def decide_proposal(analysis_id, payload):
    value = get_object_or_404(Request.objects.select_for_update(), pk=analysis_id, deleted_at__isnull=True)
    ticket = get_object_or_404(ConversationTicket, request=value, pk=payload.ticket_id, active=True)
    assert_editable(ticket)
    previous = ticket.draft
    proposal = previous.get("proposal")
    if previous.get("revision") != payload.expected_revision or not proposal or proposal.get("id") != str(payload.proposal_id):
        raise HttpError(409, "The ticket proposal changed. Reload it before applying it.")
    if payload.apply:
        if proposal.get("replacement") and not payload.replace_confirmed:
            raise HttpError(409, "Confirm replacement of the existing ticket draft.")
        if proposal.get("replacement"):
            ticket.active = False
            ticket.save(update_fields=["active", "updated_at"])
            ticket = None
        draft = {**proposal, "revision":previous["revision"]+1, "scope_choice":"unknown", "saved_at":timezone.now().isoformat()}
        draft.pop("id")
        store(value, draft, ticket)
        value.discussion_state.pop("pending_ticket_clarification", None)
        value.save(update_fields=["discussion_state"])
    else:
        store(value, {**previous, "proposal":None}, ticket)
    return snapshot(value)


def create_conversational_draft(value, trigger, proposal, allowed_messages, analyses=()):
    import uuid
    allowed = {item.pk for item in allowed_messages}
    if proposal.anchor_message_id is not None and proposal.anchor_message_id not in allowed:
        raise ValueError("The proposed ticket has no authorized conversation anchor")
    allowed_sources = {f"message:{identifier}" for identifier in allowed} | {item["id"] for item in analyses}
    if not set(proposal.sources) <= allowed_sources:
        raise ValueError("The proposed ticket cites an unavailable source")
    ticket = active_ticket(value)
    previous = ticket.draft if ticket else {}
    if proposal.unchanged:
        if ticket:
            assert_editable(ticket)
            store(value, {**previous, "unchanged":True, "proposal":None}, ticket)
        return ticket
    source = source_from_output(value, proposal, allowed_sources)
    candidate = {"title":text(proposal.title, 200, configured_secrets()), "body":text(proposal.body, 30000, configured_secrets()),
                 "anchor_message_id":proposal.anchor_message_id,
                 "context_message_ids":[int(identifier.split(":")[1]) for identifier in proposal.sources if identifier.startswith("message:")],
                 "requested_by_message_id":trigger.pk, "prepared_through_message_id":trigger.pk,
                 "source_version":source.number if source else None, "scope_choice":"unknown", "generated":True}
    candidate["sources"] = proposal.sources
    if ticket and previous.get("body"):
        assert_editable(ticket)
        candidate.update(id=str(uuid.uuid4()), base_revision=previous["revision"], replacement=getattr(proposal, "replace_existing", False))
        store(value, {**previous, "proposal":candidate, "unchanged":False}, ticket)
    else:
        candidate["revision"] = previous.get("revision", 0)+1
        store(value, candidate, ticket)
    value.discussion_state.pop("pending_ticket_clarification", None)
    value.save(update_fields=["discussion_state"])
    return ticket or active_ticket(value)
