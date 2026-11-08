import json
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import PublishedTicket, Request, ResultVersion, TicketConnector
from core.ticket_publication import stored_publication_url


@pytest.mark.django_db
def test_publication_links_use_one_query_instead_of_one_connector_read_per_row(
    environment, tmp_path
):
    value = Request.objects.create(environment=environment, need="Performance fixture")
    version = ResultVersion.objects.create(request=value, number=1)
    connector = TicketConnector.objects.create(
        name="Test", platform="gitlab", base_url="https://gitlab.example"
    )
    for _ in range(20):
        row = PublishedTicket.objects.create(
            request=value,
            version=version,
            connector=connector,
            platform="gitlab",
            project="1",
            destination=str(uuid.uuid4()),
            idempotency_key=uuid.uuid4(),
            external_reference="spechelper:" + str(uuid.uuid4()),
            title="Fixture",
            body="Fixture",
            status="PUBLISHED",
        )
        PublishedTicket.objects.filter(pk=row.pk).update(
            url="https://gitlab.example/team/project/-/issues/1"
        )

    def count(related):
        rows = PublishedTicket.objects.filter(request=value).select_related(*related)
        with CaptureQueriesContext(connection) as queries:
            links = [stored_publication_url(row) for row in rows]
        assert len(links) == 20 and all(links)
        return len(queries)

    before, after = count(["version"]), count(["version", "connector"])
    assert before == 21 and after == 1
    (tmp_path / "publication-query-budget.json").write_text(
        json.dumps({"publications": 20, "before_queries": before, "after_queries": after})
    )
