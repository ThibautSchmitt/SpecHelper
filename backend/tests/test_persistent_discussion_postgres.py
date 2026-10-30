"""Competing submissions use real PostgreSQL row locks and a disposable test database."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection, connections
from django.test import Client

from core.models import AISession, AnalysisRun, Job, Request

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


@pytest.mark.parametrize("parallel", [2, 10])
def test_browser_discussions_really_overlap_on_one_account(environment, storage, settings, monkeypatch, parallel):
    from core.models import AIConnection
    from core.providers import public
    from core.worker import claim_job, perform_job

    settings.AI_ACCOUNT_CONCURRENCY = parallel
    settings.AI_CONCURRENCY = parallel
    browsers = [Client() for _ in range(parallel + 1)]
    ids = []
    for index, browser in enumerate(browsers):
        value = browser.post("/api/analyses", {"environment_id": environment.pk, "need": f"Explain SQL export in project {index}."}, content_type="application/json").json()
        assert browser.post(f"/api/analyses/{value['id']}/analyze").status_code == 200
        ids.append(value["id"])
    jobs = [claim_job() for _ in range(parallel)]
    assert all(jobs) and claim_job() is None
    assert len({job.payload["assignment"]["connection_id"] for job in jobs}) == 1
    entered = threading.Barrier(parallel + 1)
    release = threading.Event()
    payloads = []

    def workspace(value):
        path = storage / "analysis-workspaces" / str(value.pk)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def controlled(path, payload, **kwargs):
        assert path == "/run"
        payloads.append(payload)
        entered.wait(30)
        assert release.wait(30)
        return {"session_id": str(uuid.uuid4()), "output": {"message": "A scoped response."}}

    def run(pk):
        close_old_connections()
        try:
            perform_job(Job.objects.get(pk=pk))
        finally:
            connections.close_all()

    monkeypatch.setattr("core.git.request_workspace", workspace)
    monkeypatch.setattr("core.discussion.runtime_call", controlled)
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [pool.submit(run, job.pk) for job in jobs]
        try:
            entered.wait(30)
            assert len(payloads) == parallel
            assert len({p["context_id"] for p in payloads}) == parallel
            assert len({p["workspace"] for p in payloads}) == parallel
            assert all(p["session_id"] is None for p in payloads)
            assert public(AIConnection.objects.get(pk=1))["active_executions"] == parallel
            assert Job.objects.filter(status="RUNNING").count() == parallel
            assert not AnalysisRun.objects.exists()
            for payload in payloads:
                other = next(value for value in payloads if value is not payload)
                own = Request.objects.get(pk=payload["request_id"])
                other_need = Request.objects.get(pk=other["request_id"]).need
                assert own.need in payload["prompt"] and other_need not in payload["prompt"]
        finally:
            release.set()
            for future in futures:
                future.result(30)
    assert Job.objects.filter(status="DONE").count() == parallel
    assert public(AIConnection.objects.get(pk=1))["active_executions"] == 0
    assert claim_job().target == ids[parallel]
