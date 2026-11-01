"""Editable conversation drafts, separate from immutable results and publication."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja.errors import HttpError

from .models import Request
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


def snapshot(value, draft=None, *, source=None):
    secrets = configured_secrets()
    def clean(content, maximum):
        return text(content, maximum, secrets)

    draft = draft if draft is not None else value.discussion_state.get("ticket_preparation", {})
    source = source or result_for(value, draft.get("source_version"))
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
    followups = [clean(m.content, 2000) for m in reversed(list(inputs.order_by("-id")[:8]))]
    checked = verified(source)
    choice = draft.get("scope_choice", "unknown")
    fr = value.language == "fr"
    default_body = ("## Besoin" if fr else "## Need") + "\n\n" + scope
    if summary:
        default_body += ("\n\n## Constats de l’analyse" if fr else "\n\n## Analysis findings") + "\n\n" + summary
    if followups:
        default_body += ("\n\n## Précisions et demandes ajoutées — non vérifiées" if fr
                         else "\n\n## Additional requests and clarifications — unverified")
        default_body += "\n\n" + "\n\n".join(followups)
    title = clean(draft.get("title") or (source.ticket.get("title") or source.explanation.get("title") if source else "")
                  or value.display_title or value.need.splitlines()[0], 200)
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
    draft = {"revision": previous.get("revision", 0) + 1,
             "discussion_revision": state.get("revision", 0),
             "source_version": source.number if source else None,
             "scope_choice": payload.scope_choice,
             "title": text(payload.title.strip(), 200, secrets), "body": text(payload.body, 30000, secrets),
             "saved_at": timezone.now().isoformat()}
    value.discussion_state = {**state, "ticket_preparation": draft}
    value.save(update_fields=["discussion_state", "updated_at"])
    return snapshot(value, draft, source=source)
