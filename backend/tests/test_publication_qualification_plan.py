"""The opt-in bench must reject changed drafts and fence duplicate test writes."""

import hashlib
import importlib.util
import json
import uuid
from pathlib import Path

import pytest

from core.models import (
    ConversationTicket,
    PublishedTicket,
    Request,
    TicketConnector,
    TicketPublicationDraft,
)

path = Path(__file__).resolve().parents[2] / "scripts/evaluation/publication_qualification.py"
spec = importlib.util.spec_from_file_location("publication_qualification", path)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.fixture
def reviewed_case(environment):
    conversation = Request.objects.create(environment=environment, need="Neutral qualification fixture")
    ticket = ConversationTicket.objects.create(request=conversation, draft={"title": "Fixture", "body": "Reviewed body"})
    connector = TicketConnector.objects.create(name="Test GitLab", platform="gitlab", base_url="https://gitlab.example")
    draft = TicketPublicationDraft.objects.create(
        conversation_ticket=ticket, connector=connector, project="2",
        content={"title": "Fixture", "body": "Reviewed body", "fields": {}, "labels": [], "assignees": [],
                 "options_revision": "fixture", "selected_attachments": []},
    )
    return draft, {"draft_id": str(draft.pk), "revision": draft.revision, "idempotency_key": str(uuid.uuid4()),
                   "platform": "gitlab", "scenario": "double_confirmation", "title": "Fixture",
                   "body_sha256": hashlib.sha256(b"Reviewed body").hexdigest(),
                   "attachment_sha256": [], "acknowledge_unverified": True}


def test_plan_requires_explicit_confirmation_before_loading_application_data(tmp_path):
    source = tmp_path / "plan.json"
    source.write_text(json.dumps({"schema_version": 1, "confirmation": "pending", "cases": []}))
    with pytest.raises(ValueError, match="explicit plan confirmation"):
        bench.load_plan(source)


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["revision", "body", "attachment"])
def test_changed_review_cannot_reach_a_provider(reviewed_case, change):
    draft, case = reviewed_case
    if change == "revision":
        draft.revision += 1
    elif change == "body":
        draft.content["body"] = "Changed after review"
    else:
        draft.content["selected_attachments"] = [{"sha256": "f" * 64}]
    draft.save()
    with pytest.raises(ValueError, match="changed"):
        bench.reviewed_payload(case)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("resumed", [False, True])
def test_write_fence_blocks_duplicate_or_resumed_creations(reviewed_case, tmp_path, monkeypatch, resumed):
    draft, case = reviewed_case
    writes = []

    class FakeGitLab:
        def __init__(self, connector):
            self.connector = connector

        def create(self, project, payload, reference):
            writes.append(project)
            return {"external_id": "1", "external_key": "1", "url": "https://gitlab.example/team/test/-/issues/1"}

    if resumed:
        PublishedTicket.objects.create(
            request=draft.conversation_ticket.request, conversation_ticket=draft.conversation_ticket,
            connector=draft.connector, platform="gitlab", project="2", destination="fixture",
            idempotency_key=case["idempotency_key"], external_reference="spechelper:fixture",
            title="Fixture", body="Reviewed body", status="UNCERTAIN",
        )

    def unsafe_publish(version, connector, payload):
        # Deliberately faulty transport caller: the bench must stop the second
        # write, and must stop even the first when reconciling an existing issue.
        provider = FakeGitLab(connector)
        provider.create("2", payload, "spechelper:fixture")
        provider.create("2", payload, "spechelper:fixture")
        raise AssertionError("The duplicate write fence was bypassed")

    monkeypatch.setattr("core.ticket_providers.provider_for", FakeGitLab)
    monkeypatch.setattr("core.ticket_publication.publish", unsafe_publish)
    report = tmp_path / "report.json"
    assert bench.run({"cases": [case]}, report, workers=1) is False
    result = json.loads(report.read_text())["cases"][0]
    assert result["status"] == "FAIL"
    assert result["create_attempts"] > result["create_budget"]
    assert len(writes) == (0 if resumed else 1)
