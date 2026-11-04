"""Read-only Markdown deliverables from saved drafts and frozen analysis results."""

from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from .artifacts import GOAL_CONSTRAINTS, section
from .business_outputs import summary_markdown
from .i18n import translate
from .models import AnalysisRun, ConversationTicket, Request, ResultVersion
from .sensitive_data import configured_secrets, redact
from .ticket_preparation import verified


def verification_note(version, language):
    if verified(version):
        return translate("Relevant deep analysis available", language)
    return translate(
        "Partial or independently unverified deliverable. Review the limits before implementation.",
        language,
    )


def result_report(analysis_id, number, kind):
    from .conversation_sources import version_records
    from .evidence_rendering import render_evidence
    from .question_actions import source_need
    from .question_outputs import render_document
    from .report_sources import render_sources

    version = get_object_or_404(
        ResultVersion.objects.select_related("request", "run"),
        request_id=analysis_id,
        request__deleted_at__isnull=True,
        number=number,
    )
    language = version.language
    if not any(
        (
            version.ticket,
            version.explanation,
            version.technical_summary,
            version.evidence.get("claims"),
        )
    ):
        raise HttpError(422, "No usable result")
    sources = version_records(version)["sources"]
    if version.explanation:
        try:
            content = render_document(
                version.explanation, version.baseline, kind, language, sources=sources
            )
        except ValueError as exc:
            raise HttpError(
                422, "This answer cannot be exported safely. Continue the question to revise it."
            ) from exc
    else:
        ticket = version.ticket
        lines = ["# " + str(ticket.get("title") or source_need(version)), ""]
        lines += section("Need", source_need(version), language)
        if kind == "business":
            lines += [summary_markdown(version.business_summary, language)]
            keys = [
                ("context", "Context"),
                ("need", "Need"),
                ("expected_behavior", "Expected behavior"),
                ("acceptance_criteria", "Acceptance criteria"),
                ("risks", "Considerations"),
            ]
        else:
            if version.technical_summary:
                lines += section("Technical summary", version.technical_summary, language)
            keys = [
                ("technical_impact", "Technical impact"),
                ("proposed_solution", "Proposed solution"),
                ("risks", "Considerations"),
                ("acceptance_criteria", "Acceptance criteria"),
            ]
        for key, label in keys:
            if ticket.get(key):
                lines += section(label, ticket[key], language)
        if version.evidence:
            lines += [
                render_evidence(
                    version.evidence, language, include_source_details=kind == "technical"
                )
            ]
        lines += [render_sources(sources, kind, language)]
        content = "\n".join(lines)
    note = verification_note(version, language)
    limits = version.evidence.get("limitations", [])
    prefix = "> " + note + "\n\n"
    if limits:
        prefix += "\n".join("> " + str(limit).replace("\n", "\n> ") for limit in limits) + "\n\n"
    return output(
        f"analysis-{analysis_id}-v{number}-{kind}.md",
        prefix + content,
        language,
        source_version=number,
        verified=verified(version),
    )


def interrupted_report(analysis_id, number, kind):
    from .conversation import role_reviews
    from .conversation_sources import collect
    from .report_sources import render_sources

    run = get_object_or_404(
        AnalysisRun.objects.select_related("request"),
        request_id=analysis_id,
        request__deleted_at__isnull=True,
        number=number,
    )
    reviews = role_reviews(run.orchestration)
    if run.status not in {"ERROR", "CANCELLED", "PARTIAL", "READY"} or not any(
        review["summary"] or review["findings"] or review["issues"] or review["limits"]
        for review in reviews
    ):
        raise HttpError(422, "No usable result")
    language = run.request.language
    lines = [
        "# " + translate("Business report" if kind == "business" else "Technical report", language),
        "",
        "> " + verification_note(None, language),
        "",
    ]
    subject = run.context_snapshot.get("dossier", {}).get("need")
    if subject:
        lines += section("Need", subject, language)
    roles = {"analyst": "Analyst", "counter_analyst": "Counter-analyst", "verifier": "Verifier"}
    for review in reviews:
        lines += [
            "## " + translate(roles[review["public_role"]], language),
            "",
            review["summary"],
            "",
        ]
        lines += section(
            "Recorded findings", [item["statement"] for item in review["findings"]], language
        )
        if review["issues"]:
            lines += section("Review disagreements", review["issues"], language)
        if review["limits"]:
            lines += section("Important limits and pending checks", review["limits"], language)
    evidence = {**run.orchestration.get("evidence", {})}
    evidence["claims"] = [
        *evidence.get("claims", []),
        *[finding for review in reviews for finding in review["findings"]],
    ]
    records = collect(
        run.request, "", {"context_usage": run.context_usage}, run.context_snapshot, evidence
    )["sources"]
    lines += [render_sources(records, kind, language)]
    return output(
        f"analysis-{analysis_id}-run{number}-{kind}-partial.md",
        "\n".join(lines),
        language,
        run_number=number,
        verified=False,
    )


def goal_document(analysis_id, ticket_id=None, source_version=None):
    value = get_object_or_404(Request, pk=analysis_id, deleted_at__isnull=True)
    version = None
    if ticket_id:
        ticket = get_object_or_404(
            ConversationTicket.objects.select_related("source_version__run", "request"),
            pk=ticket_id,
            request=value,
        )
        title, body = ticket.draft.get("title", ""), ticket.draft.get("body", "")
        version = ticket.source_version
        # A draft may contain later requirements or manual edits, even with a source result.
        from .ticket_preparation import publication_requires_ack

        checked = not publication_requires_ack(ticket)
    elif source_version is not None:
        version = get_object_or_404(
            value.versions.select_related("request", "run"), number=source_version
        )
        stored = version.artifacts.filter(name="goal.md").first()
        if stored and stored.content.strip():
            return output(
                "goal.md",
                "> " + verification_note(version, value.language) + "\n\n" + stored.content,
                value.language,
                source_version=source_version,
                verified=verified(version),
            )
        from .question_actions import source_need

        title = source_need(version)
        body = "\n\n".join(
            filter(
                None,
                [
                    version.explanation.get("summary", ""),
                    version.explanation.get("business_explanation", ""),
                    version.ticket.get("need", ""),
                ],
            )
        )
        checked = verified(version)
    else:
        from .deep_analysis_context import suggested_need

        title, body = suggested_need(value), ""
        checked = False
    if not str(title).strip():
        raise HttpError(422, "Describe the need to investigate.")
    language = value.language
    note = translate(
        "Relevant deep analysis available" if checked else "Without deep verification", language
    )
    lines = ["# goal.md", "", "> " + note, ""]
    lines += section("Objective", title, language)
    if body:
        lines += section("Need and acceptance criteria", body, language)
    lines += section(
        "Implementation constraints",
        [translate(item, language) for item in GOAL_CONSTRAINTS],
        language,
    )
    lines += section(
        "Tests expected",
        translate(
            "Derive tests from the stated acceptance criteria. Missing criteria must be clarified before implementation.",
            language,
        ),
        language,
    )
    lines += section(
        "Uncertainties and verification limits",
        translate(
            "This document restates the selected need; it does not establish new technical facts. Clarify missing scope, behavior and decisions. Recheck sources before implementation.",
            language,
        ),
        language,
    )
    if version:
        lines += [
            f"[{translate('Source analysis', language)}](/analyses/{analysis_id}?version={version.number})",
            "",
        ]
        if version.evidence.get("limitations"):
            lines += section(
                "Important limits and pending checks", version.evidence["limitations"], language
            )
    return output(
        "goal.md",
        "\n".join(lines),
        language,
        source_version=version.number if version else None,
        verified=checked,
    )


def output(name, content, language, **metadata):
    return {
        "name": name,
        "content": redact(content, configured_secrets()),
        "language": language,
        **metadata,
    }
