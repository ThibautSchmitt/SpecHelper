"""Competing submissions use real PostgreSQL row locks and a disposable test database."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection, connections
from django.test import Client

from core.models import AISession, AnalysisRun, Job

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def postgres_required():
    if connection.vendor != "postgresql":
        pytest.skip("Requires real PostgreSQL row locks")


def competing(client, environment, operations):
    response = client.post(
        "/api/analyses",
        {
            "environment_id": environment.pk,
            "need": "Explain the SQL export in this project.",
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    value = response.json()
    cookies = client.cookies.copy()
    barrier = threading.Barrier(2)

    def submit(operation):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '10s'")
            browser = Client()
            browser.cookies = cookies.copy()
            barrier.wait(timeout=5)
            endpoint, payload = operation
            return browser.post(
                f"/api/analyses/{value['id']}/{endpoint}", payload, content_type="application/json"
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, operations))
    assert sorted(results) == [200, 409]
    assert Job.objects.filter(target=value["id"], status="QUEUED").count() == 1
    return value


def test_concurrent_turns_append_one_message_and_native_session(client, environment, storage):
    competing(
        client,
        environment,
        [("discussion", {"expected_revision": 0, "message": "Explain the SQL export."})] * 2,
    )
    assert AISession.objects.count() == 1
    assert Job.objects.get().kind == "discussion"
    assert not AnalysisRun.objects.exists()


def test_deep_launch_racing_with_discussion_cannot_start_both(client, environment, storage):
    competing(
        client,
        environment,
        [
            ("discussion", {"expected_revision": 0, "message": "Explain the SQL export."}),
            ("deep-analyze", {"expected_revision": 0}),
        ],
    )
