"""Controlled UI fixtures for the local development database, never a deployed instance."""

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if os.environ.get("POSTGRES_HOST") or os.environ.get("SPECHELPER_DATA_DIR"):
    raise RuntimeError("UI fixtures require an isolated local development database")
if os.environ.get("E2E_DATA_DIR"):
    fixture_data = Path(os.environ["E2E_DATA_DIR"]).resolve()
    if fixture_data.parent != ROOT / ".local" or fixture_data.name != "v14-dev-data":
        raise RuntimeError("The UI fixture data directory is not an approved development directory")
    os.environ["SPECHELPER_DATA_DIR"] = str(fixture_data)
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django  # noqa: E402

django.setup()
from core.models import (  # noqa: E402
    AIConnection,
    AISession,
    Environment,
    EnvironmentRepository,
    Job,
    Request,
)

action, target = sys.argv[1:3]
saved_ai = ROOT / ".local" / ("e2e-ai-" + target + ".json")
if action == "seed":
    saved_ai.write_text(
        json.dumps(AIConnection.objects.filter(pk=1).values("agent", "status", "account").first())
    )
    AIConnection.objects.update_or_create(pk=1, defaults={"agent": "codex", "status": "CONNECTED"})
    environment, _ = Environment.objects.get_or_create(
        name="[E2E] " + target, defaults={"status": "READY"}
    )
    EnvironmentRepository.objects.get_or_create(
        environment=environment,
        repository="fixture/contracts",
        defaults={"branch": "main", "sha": "c" * 40},
    )
    print(environment.id)
elif action == "cleanup":
    environments = Environment.objects.filter(name="[E2E] " + target)
    requests = Request.objects.filter(environment__in=environments)
    from django.conf import settings

    for request in requests:
        shutil.rmtree(settings.MEDIA_ROOT / str(request.id), ignore_errors=True)
    Job.objects.filter(kind="analysis", target__in=[str(r.id) for r in requests]).delete()
    # Delete only controlled fixture artifacts and derived requests before their protected sources.
    from core.models import QuestionDocument

    QuestionDocument.objects.filter(source_version__request__in=requests).delete()
    requests.filter(workflow="request").delete()
    requests.delete()
    environments.delete()
    if saved_ai.exists():
        previous = json.loads(saved_ai.read_text())
        if previous is None:
            AIConnection.objects.filter(pk=1).delete()
        else:
            AIConnection.objects.update_or_create(pk=1, defaults=previous)
        saved_ai.unlink()
else:
    request = Request.objects.get(pk=target, environment__name__startswith="[E2E]")
    if action == "clarify":
        request.status = "NEEDS_CLARIFICATION"
        request.questions = [
            {"id": "Q1", "question": "Should the export include active contracts only?"}
        ]
        request.understanding = "A CSV export of contracts is requested."
        request.save()
        AISession.objects.filter(request=request).update(
            runtime_id="11111111-1111-4111-8111-111111111111"
        )
    elif action == "question-result":
        from core.question_outputs import QuestionOutput
        from core.results import publish

        if request.workflow != "question":
            raise RuntimeError("Question fixtures require a question workflow")
        output = QuestionOutput.model_validate({
            "status": "READY",
            "answer": {
                "title": "Active contract validation",
                "summary": "Active contracts are validated before export.",
                "business_explanation": "Only active records can be exported.",
                "technical_explanation": "The export service applies an active-record filter.",
                "verified_facts": ["The export service checks active status."],
                "rules": ["Inactive contracts are excluded."],
                "steps": ["Select contracts", "Filter active records", "Export"],
                "examples": ["An inactive contract is omitted."],
                "dependencies": ["Contract repository"],
                "flows": ["Contract selection to CSV download"],
                "inferences": ["Historical imports may use this filter."],
                "uncertainties": ["Historical imports were not checked."],
                "references": [{"repository": "fixture/contracts", "path": "contracts/export.py", "symbol": "export_active"}],
            },
        })
        publish(request.id, request.analysis_runs.order_by("-number").first(), output)
    elif action in {"result", "derived-result"}:
        if action == "result":
            assert request.conversation[0]["answers"]["Q1"] == "Yes, active contracts only."
            assert request.session.runtime_id == "11111111-1111-4111-8111-111111111111"
        from core.artifacts import ArtifactOutput
        from core.results import publish

        output = ArtifactOutput.model_validate(
            {
                "status": "READY",
                "technical_summary": "Controlled UI fixture",
                "ticket": {
                    "title": "Export active contracts as CSV",
                    "context": "The team wants to share active contracts.",
                    "need": "Share active contracts",
                    "expected_behavior": ["Export active records only"],
                    "acceptance_criteria": ["The file contains active contracts only"],
                    "proposed_solution": "Add an export action",
                    "technical_impact": ["contracts/export.py"],
                    "risks": ["Limit volume"],
                },
                "goal": {
                    "business_intent": "Share active contracts",
                    "current_behavior": "No export available",
                    "required_behavior": ["CSV download"],
                    "technical_context": ["Export service"],
                    "relevant_files": ["contracts/export.py"],
                    "constraints": ["Do not change the database"],
                    "implementation_guidance": ["Reuse the existing selection"],
                    "acceptance_criteria": ["Active contracts only"],
                    "tests_expected": ["Verify the active filter"],
                    "useful_attachments": list(request.attachments.values_list("name", flat=True)),
                },
            }
        )
        publish(request.id, request.analysis_runs.order_by("-number").first(), output)
        print(json.dumps({"baseline": request.baseline}))
