import json
import uuid

import pytest

from core.artifacts import GOAL_CONSTRAINTS, ArtifactOutput, HumanTicket, render_goal
from core.i18n import translate
from core.models import AISession, GeneratedArtifact, Job, Request, ResultVersion
from core.results import publish

pytestmark = pytest.mark.django_db


def test_continuation_retains_session_and_creates_immutable_artifacts(client, environment, bundle):
    created = client.post(
        "/api/requests",
        data=json.dumps({"environment_id": environment.id, "need": "Export active contracts"}),
        content_type="application/json",
    )
    request = Request.objects.get(pk=created.json()["id"])
    request.status = "READY"
    request.baseline = [{"repository": "company/backend", "branch": "main", "sha": "a" * 40}]
    request.save()
    sid = str(uuid.uuid4())
    AISession.objects.create(request=request, runtime_id=sid, agent="codex")
    first = publish(request.id, None, bundle)
    original_goal = first.artifacts.get(name="goal.md").content
    response = client.post(
        f"/api/requests/{request.id}/continue",
        data=json.dumps({"message": "I do not want any database changes.", "expected_version": 1}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CONTINUING_CONVERSATION"
    request.refresh_from_db()
    assert request.session.runtime_id == sid
    assert request.messages.get(kind="followup").content == "I do not want any database changes."
    assert Job.objects.get().analysis_run.request_id == request.id
    assert (
        client.post(
            f"/api/requests/{request.id}/continue",
            data=json.dumps({"message": "A duplicate", "expected_version": 1}),
            content_type="application/json",
        ).status_code
        == 409
    )
    environment.repositories.update(sha="b" * 40)
    # Direct rendering fixtures still require a valid current execution fence;
    # they do not pretend that independent AI review has completed.
    from core.worker import claim_job

    assert claim_job() is not None
    second = publish(request.id, Job.objects.get().analysis_run, bundle)
    assert second.status == "PARTIAL"
    assert second.number == 2
    assert second.baseline == first.baseline
    assert first.artifacts.get(name="goal.md").content == original_goal
    assert "a" * 40 in second.artifacts.get(name="goal.md").content
    assert translate(GOAL_CONSTRAINTS[0], request.language) in original_goal
    assert "## " + translate("Tests expected", request.language) in original_goal
    assert "## " + translate("Repositories and baseline SHAs", request.language) in original_goal
    assert (
        "## " + translate("Repositories and baseline SHAs", request.language)
        not in first.artifacts.get(name="ticket.md").content
    )
    assert ResultVersion.objects.filter(request=request).count() == 2
    old = client.get(f"/api/requests/{request.id}/versions/1").json()
    assert old["number"] == 1 and old["goal_markdown"] == original_goal
    download = client.get(old["artifacts"]["goal.md"])
    assert download.content.decode() == original_goal
    assert 'filename="goal.md"' in download["Content-Disposition"]
    request.status = "READY"
    request.save()
    assert (
        client.post(
            f"/api/requests/{request.id}/continue",
            data=json.dumps({"message": "Outdated tab", "expected_version": 1}),
            content_type="application/json",
        ).status_code
        == 409
    )
    with pytest.raises(ValueError, match="immutable"):
        first.save()
    artifact = GeneratedArtifact.objects.get(version=first, name="goal.md")
    with pytest.raises(ValueError, match="immutable"):
        artifact.save()


def test_ticket_limit_and_no_private_reasoning(bundle):
    bad = bundle.ticket.model_dump()
    bad["context"] = "mot " * 701
    with pytest.raises(ValueError):
        HumanTicket.model_validate(bad)
    with pytest.raises(ValueError):
        ArtifactOutput.model_validate(
            {**bundle.model_dump(), "private_reasoning": "NEVER EXPORTED"}
        )
    goal = bundle.goal.model_dump()
    goal["useful_attachments"] = ["unknown.pdf"]
    with pytest.raises(ValueError, match="unknown"):
        render_goal(goal, [], [])


def test_profiles_and_skills_are_available_but_not_editable_by_agents(client):
    profiles = client.get("/api/agents").json()
    assert {p["slug"] for p in profiles} == {
        "requirement",
        "code",
        "attachment",
        "reviewer",
        "writer",
    }
    skills = client.get("/api/skills").json()
    assert {
        "codebase-navigation",
        "git-history-analysis",
        "impact-analysis",
        "minimal-change",
        "postgres-readonly-analysis",
        "attachment-analysis",
        "project-conventions",
    } <= {s["slug"] for s in skills}
    assert client.post("/api/agents", data="{}", content_type="application/json").status_code == 405
