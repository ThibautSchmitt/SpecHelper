"""One active document, native drafting and user-reviewed updates; no deep cycle."""
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from core import discussion, environment_context
from core.models import (
    AIConnection,
    AISession,
    AnalysisRun,
    ConversationTicket,
    Job,
    Request,
    RequestMessage,
    ResultVersion,
)
from core.providers import bind_session

pytestmark = pytest.mark.django_db


@pytest.fixture
def thread(environment, storage, monkeypatch):
    value = Request.objects.create(environment=environment, need="Correct contribution rounding", status="DISCUSSING", language="en",
        analysis_protocol="2.4", discussion_state={"enabled":True,"mode":"discussion","revision":1})
    RequestMessage.objects.create(request=value, role="user", kind="discussion", content="Round contributions only after aggregation.")
    session = bind_session(value, AIConnection.objects.get(pk=1), "d-shared")
    session.runtime_id = str(uuid4())
    session.save()
    value.discussion_state.update(session_pk=session.pk, connection_id=1)
    value.save()
    def workspace(row):
        path = storage / "workspaces" / str(row.pk)
        path.mkdir(parents=True, exist_ok=True)
        return path
    monkeypatch.setattr("core.git.request_workspace", workspace)
    return value


def endpoint(value):
    return f"/api/analyses/{value.pk}/ticket-preparation"


def enqueue(client, value, purpose="prepare", **extra):
    draft = client.get(endpoint(value)).json()
    return client.post(endpoint(value)+"/generate", {"ticket_id":draft["id"], "expected_revision":draft["revision"],
        "expected_discussion_revision":draft["discussion_revision"], "purpose":purpose, **extra}, content_type="application/json")


def complete(value, output, check=None):
    job = Job.objects.filter(target=str(value.pk),kind="discussion").latest("id")
    job.status="RUNNING"
    job.save()
    def native(path, payload, **kwargs):
        assert payload["persistent_conversation"] and payload["session_id"]
        if check:
            check(payload)
        return {"session_id":payload["session_id"], "output":output}
    discussion.run_job(job, native)
    job.refresh_from_db()
    return job


def initial(client, value):
    assert enqueue(client, value).status_code == 200
    assert complete(value, {"title":"Contribution rounding", "body":"Round the sum, not every item.", "sources":[]}).status == "DONE"
    return client.get(endpoint(value)).json()


def decide(client, value, draft, apply, **extra):
    return client.post(endpoint(value)+"/proposal", {"ticket_id":draft["id"],"expected_revision":draft["revision"],
        "proposal_id":draft["proposal"]["id"], "apply":apply, **extra},content_type="application/json")


def test_prepare_is_one_native_call_and_double_click_cannot_create_a_second_draft(client, thread):
    assert enqueue(client, thread).status_code == 200
    assert enqueue(client, thread).status_code == 200
    assert ConversationTicket.objects.filter(request=thread, active=True).count()==1
    assert Job.objects.filter(target=str(thread.pk)).count()==1
    assert complete(thread, {"title":"Contribution rounding","body":"Round after aggregation.","sources":[]}).status=="DONE"
    draft=client.get(endpoint(thread)).json()
    assert draft["title"]=="Contribution rounding" and not draft["initial_pending"]
    assert not thread.messages.filter(kind="ticket_preparation",role="assistant").exists()
    assert not AnalysisRun.objects.exists() and not ResultVersion.objects.exists()
    assert AISession.objects.count()==1
    with pytest.raises(IntegrityError),transaction.atomic():
        ConversationTicket.objects.create(request=thread,draft={"title":"Second"})


@pytest.mark.parametrize("apply", [False,True])
def test_refresh_is_a_reviewable_proposal_and_keeps_one_draft(client, thread, apply):
    original=initial(client,thread)
    assert enqueue(client,thread,"refresh").status_code==200
    assert complete(thread,{"title":"Contribution rounding","body":"Round after aggregation, including adjustments.","sources":[]}).status=="DONE"
    draft=client.get(endpoint(thread)).json()
    assert draft["body"]==original["body"] and draft["proposal"]["body"]!=original["body"]
    result=decide(client,thread,draft,apply)
    assert result.status_code==200,result.content
    assert result.json()["body"]==(draft["proposal"]["body"] if apply else original["body"])
    assert not result.json()["proposal"]
    assert ConversationTicket.objects.filter(request=thread).count()==1 and not AnalysisRun.objects.exists()


def test_refresh_uses_current_document_new_references_and_late_analysis_without_switching_topics(client,thread):
    original=initial(client,thread)
    for index in range(45):
        RequestMessage.objects.create(request=thread,role="user",kind="discussion",content=f"UNRELATED_EXPORT_{index}")
    latest=RequestMessage.objects.create(request=thread,role="user",kind="discussion",content="Back to contributions: include adjustments.")
    environment_context.upload_resource(thread.environment_id,SimpleUploadedFile("contributions.md",b"Round the total including adjustments.","text/plain"),thread.environment.revision)
    version=ResultVersion.objects.create(request=thread,number=1,status="PARTIAL",context_snapshot={"dossier":{"need":"Contribution rounding"}},explanation={"summary":"The calculation rounds each item."},evidence={"limitations":["Independent checks incomplete"]})
    assert enqueue(client,thread,"refresh").status_code==200
    job=Job.objects.latest("id")
    inputs=job.payload["ticket_preparation"]["inputs"]
    assert inputs["current_draft"]["body"]==original["body"]
    assert len([item for item in inputs["observations"] if item["id"].startswith("message:")])<=24
    assert inputs["observations"][-1]["id"].startswith("document:")
    assert job.payload["snapshot"]["dossier"]["baseline"]==Request.objects.get(pk=thread.pk).baseline
    import hashlib
    import json
    manifest = job.payload["snapshot"].copy()
    digest = manifest.pop("sha256")
    assert digest == hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert Request.objects.get(pk=thread.pk).context_snapshot["sha256"] == digest
    def check(payload):
        assert payload["context_resources"]
        assert "preserve manual corrections and its subject" in payload["prompt"]
        assert "Back to contributions" in payload["prompt"]
        assert "Round the sum, not every item." in payload["prompt"]
    complete(thread,{"title":"Contribution rounding","body":"Round contributions after adjustments.","sources":["analysis:1",f"message:{latest.pk}"],"source_version":1},check)
    draft=client.get(endpoint(thread)).json()
    assert draft["body"]==original["body"]
    updated=decide(client,thread,draft,True).json()
    assert updated["source_version"]==version.number and not updated["source_verified"]
    assert "EXPORT" not in updated["body"] and ConversationTicket.objects.count()==1


def test_unchanged_or_failed_refresh_preserves_manual_corrections(client,thread):
    draft=initial(client,thread)
    assert enqueue(client,thread,"refresh").status_code==200
    complete(thread,{"unchanged":True,"sources":[]})
    kept=client.get(endpoint(thread)).json()
    assert kept["unchanged"] and kept["body"]==draft["body"]
    assert enqueue(client,thread,"refresh").status_code==200
    job=Job.objects.latest("id")
    job.status="RUNNING"
    job.save()
    discussion.fail(job,"The selected assistant is unavailable.")
    assert client.get(endpoint(thread)).json()["body"]==draft["body"]


def test_manual_save_invalidates_a_delayed_ai_proposal(client,thread):
    initial(client,thread)
    assert enqueue(client,thread,"refresh").status_code==200
    current=client.get(endpoint(thread)).json()
    saved=client.put(endpoint(thread),{"ticket_id":current["id"],"expected_revision":current["revision"],
       "expected_discussion_revision":current["discussion_revision"],"title":current["title"],"body":"My manual correction"},content_type="application/json")
    assert saved.status_code==200,saved.content
    assert complete(thread,{"title":"Contribution rounding","body":"Delayed update","sources":[]}).status=="ERROR"
    assert client.get(endpoint(thread)).json()["body"]=="My manual correction"


def test_replacement_requires_confirmation_and_preserves_old_content_until_success(client,thread):
    draft=initial(client,thread)
    assert enqueue(client,thread,"replace").status_code==409
    assert client.get(endpoint(thread)).json()["body"]==draft["body"]
    assert enqueue(client,thread,"replace",replace_confirmed=True).status_code==200
    assert client.get(endpoint(thread)).json()["body"]==draft["body"]
    complete(thread,{"title":"Exports","body":"Export only active contracts.","sources":[]})
    changed=client.get(endpoint(thread)).json()
    assert changed["id"]!=draft["id"] and changed["title"]=="Exports"
    assert ConversationTicket.objects.filter(active=True).count()==1
    assert ConversationTicket.objects.get(pk=draft["id"]).draft["body"]==draft["body"]


def test_ambiguous_need_asks_one_question_and_keeps_existing_draft(client,thread):
    original=initial(client,thread)
    assert enqueue(client,thread,"refresh").status_code==200
    complete(thread,{"clarification":"Which contribution rule should change?","sources":[]})
    assert thread.messages.filter(content="Which contribution rule should change?").count()==1
    kept=client.get(endpoint(thread)).json()
    assert kept["body"]==original["body"] and kept["clarification"]
    assert not AnalysisRun.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_prepare_requests_share_the_active_draft(environment):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections, connection, connections

    from core.ticket_api import TicketDraftGenerationIn
    from core.ticket_preparation import generate
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    value=Request.objects.create(environment=environment,need="Contribution rounding",status="DISCUSSING",
        discussion_state={"enabled":True,"mode":"discussion","revision":0})
    RequestMessage.objects.create(request=value,role="user",kind="discussion",content=value.need)
    def prepare(actor):
        close_old_connections()
        try:
            return generate(value.pk,TicketDraftGenerationIn(expected_revision=0,expected_discussion_revision=0,purpose="prepare"),actor).pk
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert set(executor.map(prepare,["browser-one","browser-two"]))=={value.pk}
    assert ConversationTicket.objects.filter(request=value,active=True).count()==1
    assert Job.objects.filter(target=str(value.pk),kind="discussion").count()==1


def test_drafting_keeps_public_findings_from_an_interrupted_analysis(client,thread):
    AnalysisRun.objects.create(request=thread, number=1, status="ERROR", orchestration={"outputs":{
        "analyst":{"claims":[{"statement":"Rounding happens per line before aggregation.","sources":[]}],"private_reasoning":"NEVER_INCLUDE_PRIVATE_REASONING"}}})
    assert enqueue(client,thread).status_code==200
    job=Job.objects.latest("id")
    observations=job.payload["ticket_preparation"]["inputs"]["observations"]
    report=next(item for item in observations if item["id"].startswith("run:1:"))
    assert "Rounding happens per line" in str(report)
    assert "NEVER_INCLUDE_PRIVATE_REASONING" not in str(observations)
    assert complete(thread,{"title":"Contribution rounding","body":"Round after aggregation. Independent verification remains incomplete.","sources":[report["id"]]}).status=="DONE"
    draft=client.get(endpoint(thread)).json()
    assert not draft["source_verified"] and draft["source_version"] is None
    assert AnalysisRun.objects.count()==1


def test_conversational_new_subject_proposes_replacement_without_overwriting_the_draft(client,thread):
    original=initial(client,thread)
    current=client.get(endpoint(thread)).json()
    response=client.post(f"/api/analyses/{thread.pk}/discussion",{"message":"Prepare a ticket for the export problem instead.","expected_revision":current["discussion_revision"]},content_type="application/json")
    assert response.status_code==200,response.content
    complete(thread,{"message":"A replacement is ready for review.","ticket":{"title":"Export contracts","body":"Export active contracts only.","sources":[],"replace_existing":True}})
    proposed=client.get(endpoint(thread)).json()
    assert proposed["body"]==original["body"] and proposed["proposal"]["replacement"]
    assert ConversationTicket.objects.count()==1
    assert decide(client,thread,proposed,True).status_code==409
    applied=decide(client,thread,proposed,True,replace_confirmed=True)
    assert applied.status_code==200,applied.content
    assert applied.json()["body"]=="Export active contracts only."
    assert applied.json()["id"]!=original["id"]
    assert ConversationTicket.objects.filter(active=True).count()==1
    assert ConversationTicket.objects.get(pk=original["id"]).draft["body"]==original["body"]
    assert not AnalysisRun.objects.exists()
