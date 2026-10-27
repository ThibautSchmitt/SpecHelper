"""Historical answer to current-source review, edited preview and unique delivery."""

import copy
import uuid
from unittest.mock import patch

import pytest
from test_ticket_publication import publication_context as _publication_context
from test_v24_omissions import committed_source as _committed_source
from test_v24_omissions import report, verification

from core.git import run as git
from core.models import PublishedTicket, Request, ResultVersion
from core.ticket_providers import NetworkUncertain
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db
publication_context, committed_source = _publication_context, _committed_source


def post(client, path, payload, method="post"):
    response = getattr(client, method)(path, payload, content_type="application/json")
    assert response.status_code in {200, 201}, response.content
    return response.json()


def test_historical_question_to_reviewed_ticket_recovers_timeout_without_duplicate(
    client, environment, storage, committed_source, publication_context, bundle,
):
    _, connector, provider, _ = publication_context
    parent = Request.objects.create(workflow="question", environment=environment,
                                    need="Explain contract cancellation conditions.", status="READY")
    historical = ResultVersion.objects.create(
        request=parent, number=1, status="READY", language="en", environment_name=environment.name,
        explanation={"title": "Cancellation conditions", "summary": "Ordinary cancellation has a migration exception.",
                     "uncertainties": ["The desired migration review policy is not a confirmed fact."],
                     "references": [{"repository": "company/backend", "path": "policy.py", "symbol": "can_cancel"}]},
        baseline=[{"repository": "company/backend", "branch": "main", "sha": committed_source["commit"]}],
        context_snapshot={"dossier": {"need": parent.need}},
    )
    assert client.get(f"/api/questions/{parent.pk}").status_code == 200
    assert any(item["id"] == str(parent.pk) for item in client.get("/api/analyses").json()["items"])
    source = copy.deepcopy(committed_source)
    repository = storage / "company/backend"
    path = repository / "policy.py"
    path.write_text(path.read_text() + "\n# New deployment revision for the linked analysis.\n")
    git("-C", repository, "add", "policy.py")
    git("-C", repository, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture revision")
    source["commit"] = git("-C", repository, "rev-parse", "HEAD")
    assert source["commit"] != historical.baseline[0]["sha"]
    environment.repositories.update(sha=source["commit"])
    change = {"source_version": 1, "environment_id": environment.pk,
              "need": "Add manual review before migration cancellations.", "operation_id": str(uuid.uuid4())}
    first = post(client, f"/api/questions/{parent.pk}/requests", change)
    assert post(client, f"/api/questions/{parent.pk}/requests", change)["id"] == first["id"]
    child = Request.objects.get(pk=first["id"])
    assert child.source_question_version == historical and child.versions.count() == 0
    attachment = child.attachments.get()
    started = post(client, f"/api/analyses/{child.pk}/analyze", {})
    assert started["baseline"][0]["sha"] == source["commit"]
    final = bundle.model_dump()
    final["ticket"].update(title="Review migration cancellations", need=change["need"],
                           context="Operations need a controlled migration-cancellation review.",
                           expected_behavior=["Require manual review before migration cancellation."],
                           proposed_solution="Add an explicit manual-review guard to the migration path.",
                           technical_impact=["policy.py:can_cancel migration branch"],
                           acceptance_criteria=["Migration cancellation requires explicit manual review."])
    final["goal"].update(business_intent=change["need"], current_behavior="The migration path bypasses the ordinary cancellation guard.",
                         required_behavior=["Require manual review before migration cancellation."],
                         relevant_files=["policy.py:can_cancel"], technical_context=["Existing cancellation guard and migration branch"],
                         implementation_guidance=["Keep the ordinary guard and scope the new review to migration cancellations."],
                         tests_expected=["Check ordinary cancellation and migration cancellation with and without manual review."])
    outputs = [
        {"status": "READY_TO_ANALYZE", "ticket": None, "understanding": change["need"],
         "questions": [], "complexity": "standard", "intent": "feature"},
        {"observations": [{"attachment": attachment.name, "facts": ["An earlier explanation describes the migration exception."],
                           "uncertainties": ["The selected source version must be rechecked."]}], "questions": []},
        report(source), report(source, exception=True),
        {"status": "APPROVED", "summary": "Review the independently found migration branch.", "issues": [], "verification": None},
        verification(source), final,
    ]

    def invoke(path, payload, **kwargs):
        assert outputs
        return {"output": outputs.pop(0), "session_id": payload["session_id"] or str(uuid.uuid4())}

    with patch("core.worker.request_workspace", return_value=storage), patch("core.worker.runtime_call", side_effect=invoke):
        for _ in range(16):
            job = claim_job()
            if not job:
                break
            perform_job(job)
            child.refresh_from_db()
            if child.status in {"READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"}:
                break
    assert child.status == "READY", child.error
    assert not outputs
    result = child.versions.get()
    roles = {step["public_role"] for step in result.run.steps if step["status"] == "DONE"}
    assert {"analyst", "counter_analyst", "verifier"} <= roles
    endpoint = f"/api/requests/{child.pk}/versions/1"
    destination = {"connector_id": connector.pk, "project": "42", "ticket_format": "standard"}
    shown = post(client, endpoint + "/publication-preview", destination)
    assert shown["publication_allowed"] and not shown["selected_attachments"]
    provider.create.assert_not_called()
    edited = {**destination, "title": "Business-reviewed migration change", "body": shown["body"] + "\n\nReviewed by the requester.",
              "fields": shown["values"], "labels": [], "assignees": [], "options_revision": shown["revision"],
              "draft_id": shown["draft_id"], "draft_revision": shown["draft_revision"]}
    saved = post(client, endpoint + "/publication-draft", edited, method="put")
    assert saved["title"] == edited["title"] and saved["body"] == edited["body"]
    provider.create.assert_not_called()
    submitted = {**edited, "draft_revision": saved["draft_revision"],
                 "idempotency_key": str(uuid.uuid4()), "confirmed": True}
    provider.create.side_effect = NetworkUncertain("Synthetic accepted issue with a lost response")
    uncertain = post(client, endpoint + "/publications", submitted)
    assert uncertain["status"] == "UNCERTAIN"
    provider.find.return_value = {"external_id": "123", "external_key": "#1",
                                  "url": "https://gitlab.example/team/project/-/issues/1"}
    recovered = post(client, endpoint + "/publications", submitted)
    assert recovered["status"] == "PUBLISHED" and recovered["id"] == uncertain["id"]
    assert post(client, endpoint + "/publications", submitted)["id"] == recovered["id"]
    provider.create.assert_called_once()
    record = PublishedTicket.objects.get(pk=recovered["id"])
    assert record.version_id == result.pk and record.title == edited["title"]
    assert record.snapshot["baseline"][0]["sha"] == source["commit"]
    details = client.get(f"/api/analyses/{child.pk}").json()
    assert details["result_state"] == "published"
    assert details["publications"][0]["url"] == recovered["url"]
    published = client.get("/api/tickets", {"search": "Business-reviewed"}).json()
    assert published["total"] == 1 and published["items"][0]["version_number"] == 1
    historical.refresh_from_db()
    result.refresh_from_db()
    assert historical.baseline[0]["sha"] == committed_source["commit"]
    assert result.ticket["title"] == "Review migration cancellations"
    assert parent.versions.count() == 1 and parent.messages.filter(kind="derived_request").count() == 1
