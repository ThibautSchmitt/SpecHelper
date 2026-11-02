"""Legacy drafts, versions and external publication evidence survive the migration."""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_legacy_preparation_and_active_generation_keep_their_target():
    latest = MigrationExecutor(connection).loader.graph.leaf_nodes("core")
    old = [("core", "0048_database_connection_checked_at")]
    try:
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        Request = apps.get_model("core", "Request")
        Message = apps.get_model("core", "RequestMessage")
        Version = apps.get_model("core", "ResultVersion")
        Job = apps.get_model("core", "Job")
        Publication = apps.get_model("core", "PublishedTicket")
        row = Request.objects.create(need="Legacy dates", discussion_state={"enabled": True})
        topic = Message.objects.create(request=row, role="user", kind="need", content="Dates")
        version = Version.objects.create(
            request=row, number=1, explanation={"summary": "Frozen finding"}
        )
        draft = {
            "revision": 3,
            "source_version": 1,
            "topic_message_id": topic.pk,
            "title": "Fix dates",
            "body": "Keep this body",
            "sources": ["source-1"],
        }
        row.discussion_state = {"enabled": True, "ticket_preparation": draft}
        row.save()
        job = Job.objects.create(
            kind="discussion",
            target=str(row.pk),
            status="QUEUED",
            payload={"ticket_preparation": {"expected_draft_revision": 3}},
        )
        connector = apps.get_model("core", "TicketConnector").objects.create(
            name="Legacy GitLab", platform="gitlab", base_url="https://example.org"
        )
        publication = Publication.objects.create(
            request=row,
            version=version,
            connector=connector,
            platform="gitlab",
            project="42",
            destination="old-destination",
            idempotency_key=uuid.uuid4(),
            external_reference="legacy-publication",
            title="Published title",
            body="Published body",
            status="PUBLISHED",
            external_id="11",
            url="https://example.org/11",
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        ticket = current.get_model("core", "ConversationTicket").objects.get(request_id=row.pk)
        assert (
            ticket.draft == draft
            and ticket.source_version_id == version.pk
            and ticket.topic_message_id == topic.pk
        )
        value = current.get_model("core", "Request").objects.get(pk=row.pk)
        assert value.archived_at is None
        assert value.discussion_state["ticket_preparation_id"] == str(ticket.pk)
        assert value.discussion_state["ticket_preparation"] == draft
        assert current.get_model("core", "Job").objects.get(pk=job.pk).payload[
            "ticket_preparation"
        ]["conversation_ticket_id"] == str(ticket.pk)
        existing = current.get_model("core", "PublishedTicket").objects.get(pk=publication.pk)
        assert (
            existing.conversation_ticket_id is None
            and existing.body == "Published body"
            and existing.external_id == "11"
        )
        assert current.get_model("core", "ResultVersion").objects.get(
            pk=version.pk
        ).explanation == {"summary": "Frozen finding"}
    finally:
        MigrationExecutor(connection).migrate(latest)
