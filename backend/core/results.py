from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .artifacts import render_goal, render_human
from .business_outputs import BusinessOutputError, BusinessSummary, decision_rules, normative_rules
from .models import AnalysisResult, GeneratedArtifact, Job, Request, RequestMessage, ResultVersion
from .question_outputs import QuestionOutput, render_answer
from .sensitive_data import configured_secrets, redact


@transaction.atomic
def publish(request_id, run, output):
    if run and run.job_id and run.request.analysis_protocol == "2.4":
        Job.objects.select_for_update().get(pk=run.job_id)
    request = Request.objects.select_for_update().get(pk=request_id)
    if request.analysis_protocol == "2.4" and run:
        from .step_execution import check_execution

        check_execution(run)
        existing = request.versions.filter(run=run).first()
        if existing:
            run.status, run.finished_at = existing.status, existing.created_at
            run.save(update_fields=["status", "finished_at"])
            return existing
    number = (request.versions.aggregate(last=Max("number"))["last"] or 0) + 1
    output = type(output).model_validate(redact(output.model_dump(), configured_secrets()))
    if output.questions:
        raise BusinessOutputError(
            "Answer the pending business questions before publishing a result."
        )
    frozen = run.context_snapshot if run else request.context_snapshot
    decision_context = frozen.get("business_decisions", {})
    decisions = decision_context.get("decisions", [])
    rules = decision_rules(decisions)
    history = decision_context.get("history", [])
    summary = dict(run.orchestration.get("business_summary", {})) if run else {}
    proposed_summary = getattr(output, "business_summary", None)
    if proposed_summary:
        latest_summary = proposed_summary.model_dump()
        uncertain = list(
            dict.fromkeys([*summary.get("uncertainties", []), *latest_summary["uncertainties"]])
        )
        summary.update({key: value for key, value in latest_summary.items() if value})
        summary["uncertainties"] = uncertain
    if summary:
        summary = BusinessSummary.model_validate(summary).model_dump()
    output = output.model_copy(deep=True)
    evidence = {}
    if request.analysis_protocol in {"2.3", "2.4"}:
        from .analysis_evidence import ReliabilityReport, public_report
        from .permission_evidence import qualify_report

        report = ReliabilityReport.model_validate(
            run.orchestration.get("evidence", {}) if run else {}
        )
        report = qualify_report(report, run.orchestration.get("permission_limits", []) if run else [])
        evidence = public_report(report, request.language).model_dump()
        roles = {
            step.get("public_role")
            for step in (run.steps if run else [])
            if step.get("status") == "DONE"
        }
        if not {"analyst", "counter_analyst", "verifier"} <= roles or not evidence["claims"]:
            evidence["blocking"] = True
            evidence["limitations"].append(
                "Independent analysis, counter-analysis and verification have not all been completed."
            )
        if evidence["blocking"]:
            output.status = "PARTIAL"
    is_question = request.workflow == "question"
    if is_question:
        output = QuestionOutput.model_validate(output.model_dump())
        output.answer.confirmed_decisions = rules
        if summary:
            output.answer.business_summary = BusinessSummary.model_validate(summary)
        if evidence:
            output.answer.evidence = ReliabilityReport.model_validate(evidence)
        output = QuestionOutput.model_validate(output.model_dump())
        explanation = output.answer.model_dump()
        ticket = {}
        markdown = render_answer(explanation, request.baseline, request.language)
        artifacts = {"answer.md": markdown}
        technical_summary = output.answer.summary
    else:
        if rules:
            output.ticket.expected_behavior = normative_rules(
                output.ticket.expected_behavior, rules, history, decisions
            )
            output.ticket.acceptance_criteria = normative_rules(
                output.ticket.acceptance_criteria, rules, history, decisions
            )
            output.goal.required_behavior = normative_rules(
                output.goal.required_behavior, rules, history, decisions
            )
            output.goal.acceptance_criteria = normative_rules(
                output.goal.acceptance_criteria, rules, history, decisions
            )
            try:
                output = type(output).model_validate(output.model_dump())
            except ValueError as error:
                raise BusinessOutputError(
                    "The confirmed decisions exceed the ticket limits. Shorten their wording or split the request; no decisions or previous results were removed."
                ) from error
        explanation = {}
        ticket = output.ticket.model_dump()
        markdown = render_human(ticket, language=request.language, business_summary=summary)
        artifacts = {
            "ticket.md": markdown,
            "goal.md": render_goal(
                output.goal.model_dump(),
                request.baseline,
                request.attachments.all(),
                language=request.language,
                context_snapshot=frozen,
            ),
        }
        technical_summary = output.technical_summary
    if evidence and not is_question:
        from .evidence_rendering import render_evidence

        appendix = "\n" + render_evidence(evidence, request.language)
        artifacts = {
            name: content.rstrip() + "\n" + appendix for name, content in artifacts.items()
        }
        markdown = artifacts["ticket.md"]
    version = ResultVersion.objects.create(
        request=request,
        run=run,
        number=number,
        language=request.language,
        status=output.status,
        ticket=ticket,
        explanation=explanation,
        technical_summary=technical_summary,
        baseline=request.baseline,
        database_snapshot=request.database_snapshot,
        environment_name=request.environment_name_snapshot,
        format_version="1.7" if is_question else "1.6",
        context_snapshot=run.context_snapshot if run else {},
        context_usage=run.context_usage if run else [],
        decisions_snapshot=decisions,
        business_summary=summary,
        evidence=evidence,
    )
    GeneratedArtifact.objects.bulk_create(
        [
            GeneratedArtifact(version=version, name=name, content=content)
            for name, content in artifacts.items()
        ]
    )
    # Preserve the existing latest-result endpoint while versions remain append-only.
    if not is_question:
        AnalysisResult.objects.update_or_create(
            request=request, defaults={"ticket": ticket, "markdown": markdown}
        )
    RequestMessage.objects.create(
        request=request,
        role="assistant",
        kind="result",
        content=f"Result v{number} available.",
        version=version,
    )
    request.status, request.error, request.questions = output.status, "", []
    request.progress += [{"label": f"Result v{number} available", "at": timezone.now().isoformat()}]
    request.save(update_fields=["status", "error", "questions", "progress", "updated_at"])
    if run:
        run.status, run.finished_at = output.status, timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return version
