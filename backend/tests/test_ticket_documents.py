import copy
import json
from uuid import uuid4

import pytest
from test_ticket_publication import publication_context as publication_context

from core import discussion
from core.models import AIConnection, AnalysisRun, ConversationTicket, Job, RequestMessage
from core.providers import bind_session

pytestmark = pytest.mark.django_db


@pytest.fixture
def documents(client, publication_context, monkeypatch, storage):
    version, connector, provider, _ = publication_context
    value = version.request
    value.status, value.language = "DISCUSSING", "fr"
    session = bind_session(value, AIConnection.objects.get(pk=1), "d-shared")
    session.runtime_id = str(uuid4())
    session.save()
    value.discussion_state = {"enabled":True,"mode":"discussion","revision":1,"connection_id":1,"session_pk":session.pk}
    value.save()
    RequestMessage.objects.create(request=value, role="user", kind="discussion", content="Implémenter les arrondis après agrégation. La fréquence reste à préciser.")
    ticket = ConversationTicket.objects.create(request=value, draft={"title":"Arrondir après agrégation", "body":"Conserver les corrections manuelles. Fréquence non définie.", "revision":1})
    provider.attachment_policy.return_value = {"enabled":True,"max_bytes":25000000}
    provider.options.return_value["fields"]=[{"id":"detail","label":"Implementation detail","type":"textarea","required":False}]
    monkeypatch.setattr("core.ticket_providers.provider_for", lambda connector:provider)
    monkeypatch.setattr("core.git.request_workspace", lambda value:storage)
    endpoint = f"/api/analyses/{value.pk}/tickets/{ticket.pk}"
    response = client.get(endpoint+"/publication-draft", {"connector_id":connector.pk,"project":"42"})
    assert response.status_code == 200, response.content
    preview = response.json()
    payload = {key:preview[key] for key in ("title","body","template_id","issue_type","ticket_format","include_business_analysis","include_technical_analysis","include_attachments","attachment_ids","include_goal","include_diagrams")}
    payload.update(conversation_ticket_id=str(ticket.pk),connector_id=connector.pk,project="42",fields=preview["values"],labels=preview["defaults"]["labels"],assignees=preview["defaults"]["assignees"],options_revision=preview["revision"],draft_id=preview["draft_id"],draft_revision=preview["draft_revision"])
    payload["fields"]["detail"]="Preserve this final destination-field edit."
    saved=client.put(endpoint+"/publication-draft",payload,content_type="application/json")
    assert saved.status_code==200,saved.content
    payload["draft_revision"]=saved.json()["draft_revision"]
    return value,ticket,provider,endpoint,payload


def start(client, documents, kinds=("goal",), **extra):
    _,_,_,endpoint,payload=documents
    return client.post(endpoint+"/documents/generate", {"draft_id":payload["draft_id"],"draft_revision":payload["draft_revision"],"documents":list(kinds),**extra},content_type="application/json")


def finish(value, kinds):
    job=Job.objects.latest("id")
    job.status="RUNNING"
    job.save()
    def native(path,payload,**kwargs):
        assert payload["database"] is None
        data=json.loads(payload["prompt"].split("UNTRUSTED CONVERSATION DATA:\n")[1])
        assert data["requested_document_kinds"]==sorted(kinds)
        assert data["final_publication_content"]["body"]=="Conserver les corrections manuelles. Fréquence non définie."
        assert data["final_publication_content"]["fields"]["detail"]=="Preserve this final destination-field edit."
        assert payload["schema"]["title"]=="TicketDocumentsReply"
        return {"session_id":payload["session_id"] or str(uuid4()),"output":{"documents":[{
            "kind":kind,"content":"# Objectif\n\nRespecter le ticket.\n\n## Périmètre\n\nArrondir après agrégation.\n\n## Informations manquantes\n\nNe pas inventer la fréquence.\n\n## Impacts possibles\n\nÀ investiguer.\n\n## Tests\n\nVérifier les arrondis.","sources":[]
        } for kind in kinds]}}
    discussion.run_job(job,native)
    job.refresh_from_db()
    assert job.status=="DONE", job.error
    return job


def test_selected_documents_are_one_lazy_call_and_cached_individually(client,documents):
    value,ticket,provider,endpoint,_=documents
    original=copy.deepcopy(ticket.draft)
    assert not Job.objects.exists()
    queued=start(client,documents).json()
    assert queued["status"]=="QUEUED"
    assert start(client,documents).json()["generation_id"]==queued["generation_id"]
    assert Job.objects.count()==1 and provider.create.call_count==0
    first=finish(value,["goal"])
    ready=client.get(endpoint+f"/documents/{first.pk}").json()
    assert list(ready["documents"])==["goal"]
    assert ready["documents"]["goal"]["name"]=="goal.md"
    assert not ready["documents"]["goal"]["verified"]
    assert start(client,documents).json()["status"]=="DONE"
    assert Job.objects.count()==1
    assert start(client,documents,["goal","business"]).status_code==200
    second=finish(value,["business"])
    assert set(second.payload["goal_generation"]["documents"])=={"goal","business"}
    assert Job.objects.count()==2 and not AnalysisRun.objects.exists()
    ticket.refresh_from_db()
    assert ticket.draft==original


def test_documents_must_finish_and_match_sources_before_external_creation(client,documents):
    value,ticket,provider,endpoint,payload=documents
    started=start(client,documents,["goal","technical"]).json()
    generations={"goal":started["generation_id"]}
    response=client.put(endpoint+"/publication-draft",{**payload,"document_generations":generations},content_type="application/json")
    assert response.status_code==404 and not provider.create.called
    job=finish(value,["goal","technical"])
    generations={kind:job.pk for kind in ["goal","technical"]}
    response=client.put(endpoint+"/publication-draft",{**payload,"document_generations":generations},content_type="application/json")
    assert response.status_code==200,response.content
    prepared=response.json()
    publish={**payload,"document_generations":generations,"draft_revision":prepared["draft_revision"],"idempotency_key":str(uuid4()),"confirmed":True,"unverified_confirmed":True}
    RequestMessage.objects.create(request=value,role="user",kind="discussion",content="Une nouvelle règle reste à intégrer.")
    rejected=client.post(endpoint+"/publications",publish,content_type="application/json")
    assert rejected.status_code==409 and not provider.create.called
    assert "sources changed" in rejected.json()["detail"]


@pytest.mark.parametrize("outcome", ["PUBLISHED", "UNCERTAIN"])
def test_generated_bytes_are_attached_once_without_an_independent_analysis(client,documents,outcome):
    from core.ticket_providers import NetworkUncertain

    value,ticket,provider,endpoint,payload=documents
    assert start(client,documents,["goal","business","technical"]).status_code==200
    job=finish(value,["business","goal","technical"])
    generations={kind:job.pk for kind in ["goal","business","technical"]}
    response=client.put(endpoint+"/publication-draft",{**payload,"document_generations":generations},content_type="application/json")
    assert response.status_code==200,response.content
    prepared=response.json()
    publish={**payload,"document_generations":generations,"draft_revision":prepared["draft_revision"],"idempotency_key":str(uuid4()),"confirmed":True,"unverified_confirmed":True}
    if outcome=="UNCERTAIN":
        provider.create.side_effect=NetworkUncertain("Lost response")
    response=client.post(endpoint+"/publications",publish,content_type="application/json")
    assert response.status_code==200,response.content
    assert response.json()["status"]==outcome
    assert provider.create.call_count==1 and provider.attach.call_count==(3 if outcome=="PUBLISHED" else 0)
    RequestMessage.objects.create(request=value,role="user",kind="discussion",content="Un autre sujet après publication.")
    provider.find.return_value=provider.create.return_value
    assert client.post(endpoint+"/publications",publish,content_type="application/json").status_code==200
    assert provider.create.call_count==1 and provider.attach.call_count==3
    assert {call.args[2]["name"] for call in provider.attach.call_args_list}=={"goal.md","rapport-metier.md","rapport-technique.md"}
    ticket.refresh_from_db()
    assert not ticket.active and not AnalysisRun.objects.exists()


def test_unsupported_destination_and_stale_draft_do_not_spend_tokens(client,documents):
    _,_,provider,_,payload=documents
    provider.attachment_policy.return_value={"enabled":False,"max_bytes":0}
    assert start(client,documents).status_code==422
    provider.attachment_policy.return_value={"enabled":True,"max_bytes":100000}
    payload["draft_revision"]+=1
    assert start(client,documents).status_code==409
    assert not Job.objects.exists() and not provider.create.called


def test_failed_generation_preserves_draft_and_allows_retry(client,documents):
    value,ticket,provider,_,_=documents
    original=copy.deepcopy(ticket.draft)
    assert start(client,documents).status_code==200
    job=Job.objects.latest("id")
    job.status="ERROR"
    job.save()
    assert start(client,documents).status_code==200
    assert Job.objects.count()==2
    ticket.refresh_from_db()
    assert ticket.draft==original and not provider.create.called
    assert not value.analysis_runs.exists()


def test_document_choices_save_without_generating_anything(client,documents):
    value,ticket,_,_,_=documents
    endpoint=f"/api/analyses/{value.pk}/ticket-preparation"
    initial=client.get(endpoint).json()
    assert initial["documents"]==["goal"]
    saved=client.put(endpoint,{"ticket_id":str(ticket.pk),"expected_revision":1,
        "expected_discussion_revision":1,"title":ticket.draft["title"],"body":ticket.draft["body"],
        "documents":["business","technical"]},content_type="application/json")
    assert saved.status_code==200,saved.content
    assert client.get(endpoint).json()["documents"]==["business","technical"]
    assert not Job.objects.exists()


def test_late_analysis_is_reused_only_when_explicitly_linked_to_this_ticket(client,documents):
    from core.models import ResultVersion
    from core.ticket_documents import context

    value,ticket,_,_,payload=documents
    job=Job.objects.create(kind="analysis",target=str(value.pk),status="DONE",payload={"ticket_proposal":{"ticket_id":str(ticket.pk)}})
    run=AnalysisRun.objects.create(request=value,job=job,number=1,status="PARTIAL")
    result=ResultVersion.objects.create(request=value,run=run,number=2,status="PARTIAL",technical_summary="Rounding implementation was inspected.",evidence={"limitations":["No complete independent verification"]})
    ResultVersion.objects.create(request=value,number=3,status="READY",technical_summary="UNRELATED_NEWER_RESULT")
    data,_=context(value,ticket,payload,None)
    analyses=[item for item in data["observations"] if item["id"].startswith("analysis:")]
    assert len(analyses)==1 and analyses[0]["id"]==f"analysis:{result.number}"
    assert "UNRELATED_NEWER_RESULT" not in json.dumps(data)
