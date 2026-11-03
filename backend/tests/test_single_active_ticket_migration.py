"""Compatibility keeps every old document and operation, with one editable draft."""
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_multiple_drafts_and_publications_survive_single_active_migration():
    latest=MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    old=[("core","0051_discussion_ticket_publication")]
    try:
        executor=MigrationExecutor(connection)
        executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        Request=apps.get_model("core","Request")
        Ticket=apps.get_model("core","ConversationTicket")
        Publication=apps.get_model("core","PublishedTicket")
        request=Request.objects.create(need="Contributions",discussion_state={"enabled":True})
        tickets=[Ticket.objects.create(request=request,draft={"title":f"Document {n}","body":f"Keep {n}","revision":1}) for n in range(3)]
        request.discussion_state={"enabled":True,"ticket_preparation_id":str(tickets[2].pk),"ticket_preparation":tickets[2].draft}
        request.save()
        connector=apps.get_model("core","TicketConnector").objects.create(name="Team Jira",platform="jira",base_url="https://jira.example")
        for n,status in enumerate(["PUBLISHED","UNCERTAIN"]):
            Publication.objects.create(request=request,conversation_ticket=tickets[n],connector=connector,platform="jira",project="TEAM",destination=f"dest-{n}",idempotency_key=uuid.uuid4(),external_reference=f"ref-{n}",title=f"Ticket {n}",body="Frozen content",status=status,external_id=str(n+1) if n==0 else "",url="https://jira.example/browse/TEAM-1" if n==0 else "")
        executor=MigrationExecutor(connection)
        executor.migrate(latest)
        current=executor.loader.project_state(latest).apps
        ActiveTicket=current.get_model("core","ConversationTicket")
        assert ActiveTicket.objects.filter(request_id=request.pk).count()==3
        assert ActiveTicket.objects.filter(request_id=request.pk,active=True).get().pk==tickets[1].pk
        assert list(ActiveTicket.objects.order_by("created_at").values_list("draft__body",flat=True))==["Keep 0","Keep 1","Keep 2"]
        assert current.get_model("core","PublishedTicket").objects.count()==2
        assert current.get_model("core","PublishedTicket").objects.get(status="PUBLISHED").url.endswith("TEAM-1")
        assert current.get_model("core","Request").objects.get(pk=request.pk).discussion_state["ticket_preparation_id"]==str(tickets[1].pk)
        with pytest.raises(IntegrityError),transaction.atomic():
            ActiveTicket.objects.create(request_id=request.pk,draft={"title":"Forbidden second active draft"})
    finally:
        MigrationExecutor(connection).migrate(latest)
