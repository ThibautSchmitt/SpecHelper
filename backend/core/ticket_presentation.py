"""Deterministic ticket presentation; never mutates evidence or invokes an AI."""

import re
import uuid

from django.db import transaction
from ninja.errors import HttpError

from .business_outputs import summary_markdown
from .models import TicketPublicationDraft

PRESENTATION_KEYS = (
    "ticket_format",
    "template_id",
    "issue_type",
    "include_business_analysis",
    "include_technical_analysis",
    "include_attachments",
    "attachment_ids",
    "include_goal",
)


def publication_blockers(version):
    blockers = []
    if version.status != "READY":
        blockers.append(
            "This analysis is partial or unusable. Complete the mandatory independent checks before publication."
        )
    if version.evidence.get("blocking"):
        blockers.extend(version.evidence.get("limitations", []))
        blockers.append("The verified evidence still contains blocking limitations.")
    if any(
        claim.get("material", True) and claim.get("status") != "supported"
        for claim in version.evidence.get("claims", [])
    ):
        blockers.append("A material conclusion lacks the required verification.")
    if version.request.analysis_protocol in {"2.3", "2.4"}:
        roles = {
            row.get("public_role")
            for row in (version.run.steps if version.run else [])
            if row.get("status") == "DONE"
        }
        missing = {"analyst", "counter_analyst", "verifier"} - roles
        labels = {
            "analyst": "Analyst",
            "counter_analyst": "Counter-analyst",
            "verifier": "Verifier",
        }
        blockers.extend("Missing independent check: " + labels[role] for role in sorted(missing))
        if not version.evidence.get("claims"):
            blockers.append("No verified claim is available for publication.")
    return list(dict.fromkeys(blockers))


def compact(value, words=65):
    """Keep complete short sentences where possible without inventing a summary."""
    text = " ".join(map(str, value)) if isinstance(value, list) else str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    pieces = text.split()
    if len(pieces) <= words:
        return text
    prefix = " ".join(pieces[:words])
    boundary = max(prefix.rfind(". "), prefix.rfind("; "))
    return prefix[: boundary + 1] if boundary > len(prefix) // 2 else prefix + "…"


def standard_body(version):
    ticket, language = version.ticket, version.language
    labels = {
        "Description": "Description",
        "Business summary": "Résumé métier",
        "Technical summary": "Résumé technique",
        "Proposed solution": "Solution proposée",
        "Critical considerations": "Restrictions importantes",
    }

    def label(value):
        return labels[value] if language == "fr" else value

    summary = version.business_summary
    sections = [
        ("Description", compact(ticket.get("context") or ticket.get("need"))),
        ("Business summary", compact(summary.get("desired") or ticket.get("need"))),
        (
            "Technical summary",
            compact(version.technical_summary or ticket.get("technical_impact", [])),
        ),
        ("Proposed solution", compact(ticket.get("proposed_solution"), 85)),
    ]
    lines = ["# " + str(ticket.get("title", "")), ""]
    for heading, text in sections:
        lines += ["## " + label(heading), "", text, ""]
    # Restrictions must not disappear merely because a concise format was chosen.
    risks = ticket.get("risks", [])
    if risks:
        lines += [
            "**" + label("Critical considerations") + "**",
            "",
            *["- " + str(risk) for risk in risks],
            "",
        ]
    return "\n".join(lines).strip()


def detailed_sections(version, presentation):
    lines = []
    if presentation.get("include_business_analysis"):
        lines += [summary_markdown(version.business_summary, version.language)]
        lines += [
            "## "
            + (
                "Analyse métier détaillée"
                if version.language == "fr"
                else "Detailed business analysis"
            ),
            "",
        ]
        for key in ("need", "expected_behavior", "acceptance_criteria"):
            value = version.ticket.get(key)
            if value:
                lines += [
                    "\n".join("- " + str(item) for item in value)
                    if isinstance(value, list)
                    else str(value),
                    "",
                ]
    if presentation.get("include_technical_analysis"):
        lines += [
            "## "
            + (
                "Analyse technique détaillée"
                if version.language == "fr"
                else "Detailed technical analysis"
            ),
            "",
            version.technical_summary,
        ]
        lines += ["- " + str(item) for item in version.ticket.get("technical_impact", [])]
    return "\n".join(lines).strip()


def suggest_choice(version, choices):
    """Use the immutable analysis intent as a suggestion, never as a restriction."""
    hint = str(
        version.ticket.get("type")
        or version.ticket.get("intent")
        or (version.run.orchestration.get("inferred_intent") if version.run else None)
        or version.request.category
    ).lower()
    aliases = {
        "feature": ("feature", "enhancement", "improvement", "story"),
        "bug": ("bug", "defect", "incident"),
        "documentation": ("documentation", "docs"),
        "improvement": ("improvement", "enhancement", "feature", "story"),
    }
    terms = aliases.get(hint, ())
    return next(
        (
            str(row["id"])
            for row in choices
            if any(term in str(row.get("name", "")).lower() for term in terms)
        ),
        "",
    )


def save_draft(version, connector, project, presentation, content, expected_revision=None):
    with transaction.atomic():
        draft, created = TicketPublicationDraft.objects.select_for_update().get_or_create(
            version=version,
            connector=connector,
            project=project,
            defaults={"presentation": presentation, "content": content},
        )
        if not created:
            if expected_revision is not None and draft.revision != expected_revision:
                raise HttpError(
                    409, "The ticket draft changed. Reload it before saving your edits."
                )
            if draft.presentation != presentation or draft.content != content:
                draft.presentation, draft.content = presentation, content
                draft.revision += 1
                draft.save(update_fields=["presentation", "content", "revision", "updated_at"])
    return draft


def draft_metadata(draft, version):
    return {
        "draft_id": str(draft.pk),
        "draft_revision": draft.revision,
        "version_id": str(version.pk),
        "version_number": version.number,
        "environment_name": version.environment_name,
        "baseline": version.baseline,
        "result_status": version.status,
        "publication_allowed": not publication_blockers(version),
        "publication_blockers": publication_blockers(version),
        **draft.presentation,
    }


def publication_reference(draft):
    return "spechelper:" + str(uuid.uuid5(draft.pk, str(draft.revision)))
