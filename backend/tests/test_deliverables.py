"""Deliverables disclose saved scope and evidence without starting agents or SQL."""

import pytest
from django.utils import timezone

from core.models import (
    AnalysisRun,
    ConversationTicket,
    GeneratedArtifact,
    Job,
    Request,
    RequestMessage,
    ResultVersion,
)

pytestmark = pytest.mark.django_db


def test_interrupted_run_exports_only_public_findings(client, environment):
    value = Request.objects.create(
        environment=environment, need="Do not substitute today's subject", language="fr"
    )
    run = AnalysisRun.objects.create(
        request=value,
        number=1,
        status="ERROR",
        context_snapshot={"dossier": {"need": "Frozen old subject."}},
        orchestration={
            "outputs": {
                "analyst": {
                    "current_behavior": "Recorded functional behavior.",
                    "claims": [{"statement": "A preliminary observation.", "sources": []}],
                    "private_reasoning": "NEVER_INCLUDE_PRIVATE_REASONING",
                    "limitations": ["Counter-analysis incomplete."],
                }
            }
        },
    )
    response = client.get(f"/api/analyses/{value.pk}/runs/{run.number}/reports/business")
    assert response.status_code == 200, response.content
    content = response.json()["content"]
    assert not response.json()["verified"] and "Livrable partiel" in content
    assert "Frozen old subject." in content and "preliminary observation" in content
    assert "NEVER_INCLUDE_PRIVATE_REASONING" not in content and "today's subject" not in content
    assert not ResultVersion.objects.exists() and not Job.objects.exists()


@pytest.fixture
def conversation(environment):
    return Request.objects.create(
        environment=environment,
        need="Correct rounding of all contribution amounts.",
        workflow="question",
        analysis_protocol="2.4",
        language="en",
        status="DISCUSSING",
        discussion_state={"enabled": True, "mode": "discussion", "revision": 1},
    )


def report(conversation, *, number=1, status="READY", **overrides):
    run = AnalysisRun.objects.create(
        request=conversation,
        number=number,
        status=status,
        steps=[
            {"public_role": role, "status": "DONE"}
            for role in ("analyst", "counter_analyst", "verifier")
        ],
    )
    values = dict(
        request=conversation,
        run=run,
        number=number,
        status=status,
        language="en",
        ticket={
            "title": "Contribution rounding",
            "need": "Keep adjustments in the total.",
            "technical_impact": ["Inspect the rounding boundary."],
            "acceptance_criteria": ["Include adjustments."],
        },
        technical_summary="A technical observation for this cycle only.",
        business_summary={
            "current": "Adjustments exist.",
            "desired": "Keep adjustments.",
            "gap": "Rounding needs review.",
            "impacts": [],
            "uncertainties": [],
        },
        context_snapshot={"dossier": {"need": "Frozen contribution scope."}},
        evidence={
            "blocking": status != "READY",
            "claims": [
                {
                    "statement": "Adjustments are included.",
                    "status": "supported",
                    "scope": {},
                    "sources": [],
                }
            ],
            "limitations": ["Import behavior was not checked."] if status != "READY" else [],
        },
    )
    return ResultVersion.objects.create(**{**values, **overrides})


def test_goal_uses_only_selected_draft_and_never_starts_work(client, conversation, monkeypatch):
    RequestMessage.objects.create(
        request=conversation, role="user", kind="discussion", content="UNRELATED_NEW_SUBJECT"
    )
    ticket = ConversationTicket.objects.create(
        request=conversation,
        draft={
            "title": "Contribution rounding",
            "body": "## Acceptance criteria\n\nKeep manual adjustments.",
            "revision": 1,
            "generated": True,
        },
    )
    monkeypatch.setattr(
        "core.discussion.runtime_call", lambda *a, **k: pytest.fail("No inference for deliverables")
    )
    reply = client.get(f"/api/analyses/{conversation.pk}/goal", {"ticket_id": ticket.pk})
    assert reply.status_code == 200, reply.content
    assert reply.json()["name"] == "goal.md" and not reply.json()["verified"]
    assert "Keep manual adjustments." in reply.json()["content"]
    assert "UNRELATED_NEW_SUBJECT" not in reply.json()["content"]
    ticket.refresh_from_db()
    assert (
        ticket.draft["revision"] == 1
        and not Job.objects.exists()
        and not AnalysisRun.objects.exists()
    )


def test_reports_use_frozen_cycle_and_keep_sources_in_the_right_audience(client, conversation):
    first = report(conversation)
    receipt = {
        "query_id": "sql-" + "a" * 32 + "-" + "b" * 12,
        "sql": "SELECT COUNT(*) FROM fictional_adjustments",
        "status": "checked",
        "row_count": 1,
        "truncated": False,
    }
    first.evidence["database"] = {
        "status": "checked",
        "checks": [
            receipt,
            {
                **receipt,
                "query_id": "rejected-check",
                "status": "rejected",
                "sql": "SELECT rejected_private_data",
            },
        ],
    }
    ResultVersion.objects.filter(pk=first.pk).update(evidence=first.evidence)
    second = report(conversation, number=2)
    ResultVersion.objects.filter(pk=second.pk).update(
        ticket={"title": "UNRELATED_CYCLE", "need": "OTHER_SCOPE"}
    )
    conversation.need = "LATER_CHANGED_NEED"
    conversation.save()
    base = f"/api/analyses/{conversation.pk}/versions/1/reports/"
    business = client.get(base + "business").json()
    technical = client.get(base + "technical").json()
    assert "Frozen contribution scope." in business["content"]
    assert "Keep adjustments." in business["content"]
    assert "SELECT COUNT(*) FROM fictional_adjustments" in technical["content"]
    assert "SELECT COUNT(*)" not in business["content"]
    for result in [business, technical]:
        assert result["source_version"] == 1 and result["verified"]
        assert all(
            text not in result["content"]
            for text in ["LATER_CHANGED_NEED", "UNRELATED_CYCLE", "SELECT rejected_private_data"]
        )
    assert not Job.objects.exists()


def test_partial_reports_never_upgrade_the_result(client, conversation):
    version = report(conversation, status="PARTIAL")
    response = client.get(f"/api/analyses/{conversation.pk}/versions/1/reports/technical")
    assert response.status_code == 200, response.content
    assert not response.json()["verified"]
    assert "independently unverified" in response.json()["content"]
    assert "Import behavior was not checked." in response.json()["content"]
    version.refresh_from_db()
    assert version.status == "PARTIAL"


def test_question_reports_reuse_structured_explanation(client, conversation):
    explanation = {
        "title": "A question",
        "summary": "Functional summary.",
        "business_explanation": "A functional rule.",
        "technical_explanation": "Verified technical location.",
        "uncertainties": ["One exception remains unknown."],
    }
    report(conversation, status="PARTIAL", ticket={}, explanation=explanation)
    base = f"/api/analyses/{conversation.pk}/versions/1/reports/"
    business = client.get(base + "business").json()["content"]
    technical = client.get(base + "technical").json()["content"]
    assert "A functional rule." in business and "Verified technical location." not in business
    assert "Verified technical location." in technical
    assert (
        "One exception remains unknown." in business
        and "One exception remains unknown." in technical
    )


def test_goal_retains_existing_artifact_and_new_draft_edits_stay_unverified(client, conversation):
    version = report(conversation)
    GeneratedArtifact.objects.create(
        version=version, name="goal.md", content="# Existing goal\n\nOriginal constraints."
    )
    base = f"/api/analyses/{conversation.pk}/goal"
    exported = client.get(base, {"source_version": 1}).json()
    assert exported["verified"] and "Original constraints." in exported["content"]
    ticket = ConversationTicket.objects.create(
        request=conversation,
        source_version=version,
        draft={
            "title": "Later requirement",
            "body": "Keep this user's correction.",
            "revision": 2,
            "user_edited": True,
        },
    )
    exported = client.get(base, {"ticket_id": ticket.pk}).json()
    assert not exported["verified"] and "Keep this user's correction." in exported["content"]
    assert "Original constraints." not in exported["content"]


def test_goal_without_analysis_does_not_invent_sources(client, conversation):
    RequestMessage.objects.create(
        request=conversation, role="user", kind="need", content=conversation.need
    )
    response = client.get(f"/api/analyses/{conversation.pk}/goal")
    assert response.status_code == 200, response.content
    assert not response.json()["verified"] and conversation.need in response.json()["content"]
    assert "does not establish new technical facts" in response.json()["content"]
    assert not Job.objects.exists() and not ResultVersion.objects.exists()


def test_exports_enforce_conversation_scope_archive_and_deleted_state(
    client, conversation, environment
):
    report(conversation)
    other = Request.objects.create(environment=environment, need="Other need")
    foreign = ConversationTicket.objects.create(
        request=other, draft={"title": "Other", "body": "PRIVATE"}
    )
    base = f"/api/analyses/{conversation.pk}"
    assert client.get(base + "/goal", {"ticket_id": foreign.pk}).status_code == 404
    assert client.get(base + "/versions/2/reports/business").status_code == 404
    conversation.archived_at = timezone.now()
    conversation.save()
    assert client.get(base + "/versions/1/reports/business").status_code == 200
    conversation.deleted_at = timezone.now()
    conversation.save()
    assert client.get(base + "/versions/1/reports/business").status_code == 404
    assert client.get(base + "/goal").status_code == 404
