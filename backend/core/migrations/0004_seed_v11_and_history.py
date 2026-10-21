"""Import saved v1.0 results without rewriting their historical contents."""

from django.core.exceptions import ValidationError
from django.db import migrations

from core.i18n import legacy
from core.presets_v11 import PROFILES, SKILLS


def legacy_goal(ticket, baseline, attachments):
    lines = ["# Goal", "", legacy("Historical context imported from a SpecHelper v1.0 result."), ""]
    sections = [
        ("Business intent", ticket.get("business_need", legacy("Needs clarification"))),
        ("Current behavior", ticket.get("current_behavior", legacy("Verify against the sources"))),
        ("Required behavior", ticket.get("expected_behavior", legacy("Needs clarification"))),
        (
            "Technical context",
            ticket.get("technical_analysis", legacy("Verify against the sources")),
        ),
        ("Relevant components", ticket.get("components", [])),
        ("Git baseline", [f"{r['repository']} · {r['branch']} · `{r['sha']}`" for r in baseline]),
        (
            "Constraints",
            [
                legacy("Independently verify the cited sources and symbols before making changes."),
                legacy(
                    "Preserve existing behavior outside the stated need and reuse project patterns."
                ),
                legacy("Do not refactor or clean up code unrelated to the objective."),
                legacy("Do not change the database without an explicitly established need."),
            ],
        ),
        ("Implementation guidance", ticket.get("proposed_solution", legacy("Needs clarification"))),
        ("Acceptance criteria", ticket.get("acceptance_criteria", [])),
        ("Tests expected", ticket.get("tests", [])),
        ("Useful attachments", attachments),
        ("Known uncertainties", ticket.get("risks", [])),
    ]
    for heading, value in sections:
        lines += [
            "## " + heading,
            "",
            "\n".join("- " + str(x) for x in value) if isinstance(value, list) else str(value),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def forward(apps, schema_editor):
    Skill = apps.get_model("core", "SkillDefinition")
    Profile = apps.get_model("core", "AgentProfile")
    Request = apps.get_model("core", "Request")
    Message = apps.get_model("core", "RequestMessage")
    Run = apps.get_model("core", "AnalysisRun")
    Job = apps.get_model("core", "Job")
    Result = apps.get_model("core", "AnalysisResult")
    Version = apps.get_model("core", "ResultVersion")
    Artifact = apps.get_model("core", "GeneratedArtifact")
    Attachment = apps.get_model("core", "RequestAttachment")
    for slug, (name, instructions) in SKILLS.items():
        Skill.objects.get_or_create(
            slug=slug, defaults={"name": name, "instructions": instructions}
        )
    for slug, data in PROFILES.items():
        profile, created = Profile.objects.get_or_create(
            slug=slug, defaults={k: v for k, v in data.items() if k != "skills"}
        )
        if created:
            profile.skills.set(data["skills"])
    for request in Request.objects.select_related("environment").iterator():
        if not request.environment_name_snapshot:
            request.environment_name_snapshot = (
                request.environment.name
                if request.environment_id
                else legacy("Deleted environment")
            )
            request.save(update_fields=["environment_name_snapshot"])
        if not Message.objects.filter(request=request).exists():
            Message.objects.create(
                request=request,
                role="user",
                kind="need",
                content=request.need,
                data={"legacy_import": True},
            )
            for turn in request.conversation:
                questions = turn.get("questions", [])
                answers = turn.get("answers", {})
                Message.objects.create(
                    request=request,
                    role="assistant",
                    kind="clarification",
                    content="\n".join(q["question"] for q in questions),
                    data={"questions": questions, "legacy_import": True},
                )
                Message.objects.create(
                    request=request,
                    role="user",
                    kind="answer",
                    content="\n\n".join(
                        q["question"] + "\n" + answers.get(q["id"], "") for q in questions
                    ),
                    data={"answers": answers, "legacy_import": True},
                )
            if request.questions:
                Message.objects.create(
                    request=request,
                    role="assistant",
                    kind="clarification",
                    content="\n".join(q["question"] for q in request.questions),
                    data={"questions": request.questions, "legacy_import": True},
                )
    numbers = {}
    for job in Job.objects.filter(kind="analysis").order_by("created_at", "id").iterator():
        try:
            request = Request.objects.get(pk=job.target)
        except (Request.DoesNotExist, ValueError, ValidationError):
            continue
        number = numbers.get(str(request.id), 0) + 1
        numbers[str(request.id)] = number
        Run.objects.get_or_create(
            job=job,
            defaults={
                "request": request,
                "number": number,
                "status": job.status,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "error": job.error,
            },
        )
    for result in Result.objects.select_related("request").iterator():
        request = result.request
        version, created = Version.objects.get_or_create(
            request=request,
            number=1,
            defaults={
                "format_version": "1.0",
                "status": request.status if request.status in {"READY", "PARTIAL"} else "READY",
                "ticket": result.ticket,
                "technical_summary": result.ticket.get("technical_analysis", ""),
                "baseline": request.baseline,
                "database_snapshot": request.database_snapshot,
                "environment_name": request.environment_name_snapshot,
                "run": Run.objects.filter(request=request).order_by("-number").first(),
            },
        )
        if created:
            Version.objects.filter(pk=version.pk).update(created_at=result.created_at)
            attachments = list(
                Attachment.objects.filter(request=request).values_list("name", flat=True)
            )
            Artifact.objects.create(version=version, name="ticket.md", content=result.markdown)
            Artifact.objects.create(
                version=version,
                name="goal.md",
                content=legacy_goal(result.ticket, request.baseline, attachments),
            )
            Message.objects.create(
                request=request,
                role="assistant",
                kind="result",
                content=legacy("Historical result v1 available."),
                version=version,
                data={"legacy_import": True},
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0003_v11_conversation_agents")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
