from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .artifacts import render_goal, render_human
from .models import AnalysisResult, GeneratedArtifact, Request, RequestMessage, ResultVersion
from .question_outputs import QuestionOutput, render_answer
from .sensitive_data import configured_secrets, redact


@transaction.atomic
def publish(request_id, run, output):
    request = Request.objects.select_for_update().get(pk=request_id)
    number = (request.versions.aggregate(last=Max("number"))["last"] or 0) + 1
    output = type(output).model_validate(redact(output.model_dump(), configured_secrets()))
    is_question = request.workflow == "question"
    if is_question:
        output = QuestionOutput.model_validate(output.model_dump())
        explanation = output.answer.model_dump()
        ticket = {}
        markdown = render_answer(explanation, request.baseline, request.language)
        artifacts = {"answer.md": markdown}
        technical_summary = output.answer.summary
    else:
        explanation = {}
        ticket = output.ticket.model_dump()
        markdown = render_human(ticket, language=request.language)
        artifacts = {
            "ticket.md": markdown,
            "goal.md": render_goal(
                output.goal.model_dump(),
                request.baseline,
                request.attachments.all(),
                language=request.language,
                context_snapshot=run.context_snapshot if run else {},
            ),
        }
        technical_summary = output.technical_summary
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
