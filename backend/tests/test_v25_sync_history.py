"""Successful synchronization stays inspectable outside the business activity queue."""

from unittest.mock import patch

import pytest

from core.models import Environment, Job

pytestmark = pytest.mark.django_db


def test_sync_diagnostic_history_is_bounded_scoped_redacted_and_read_only(client, environment):
    other = Environment.objects.create(name="Other", status="READY")
    for _ in range(25):
        Job.objects.create(
            kind="sync",
            target=str(environment.pk),
            status="DONE",
            payload={"credential": "must-not-be-exposed"},
        )
    Job.objects.create(
        kind="sync", target=str(other.pk), status="ERROR", error="Other environment failure"
    )
    Job.objects.create(
        kind="analysis", target=str(environment.pk), status="ERROR", error="Other kind"
    )
    failed = Job.objects.create(
        kind="sync",
        target=str(environment.pk),
        status="ERROR",
        error="Could not connect: test-only-secret",
    )
    before = list(Job.objects.values())
    with patch("core.sensitive_data.configured_secrets", return_value=["test-only-secret"]):
        response = client.get(f"/api/environments/{environment.pk}/synchronization-history")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 20 and rows[0]["id"] == failed.pk
    assert rows[0]["error"] == "Could not connect: [REDACTED]"
    assert rows[1]["status"] == "DONE"
    assert set(rows[0]) == {"id", "status", "created_at", "started_at", "finished_at", "error"}
    assert "must-not-be-exposed" not in response.content.decode()
    assert "Other environment" not in response.content.decode()
    assert list(Job.objects.values()) == before


def test_unknown_environment_has_no_sync_diagnostics(client):
    assert client.get("/api/environments/999999/synchronization-history").status_code == 404
