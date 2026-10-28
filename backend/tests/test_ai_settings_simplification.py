"""Configured role coverage and a single stable selection priority."""

import importlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.apps import apps
from django.db import connection
from ninja.errors import HttpError

from core.models import AIConnection, AIIdentity, Job, Request
from core.orchestration import role_coverage
from core.providers import candidates
from core.services import enqueue_analysis

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_connections():
    AIConnection.objects.all().delete()


def assistant(**values):
    identity = AIIdentity.objects.create(status="CONNECTED", availability="AVAILABLE")
    return AIConnection.objects.create(
        **{"identity": identity, "status": "CONNECTED", "availability": "AVAILABLE", **values}
    )


def test_priority_migration_preserves_order_and_connections():
    a = assistant(preference=3)
    b = assistant(preference=999, is_default=True, roles=["verifier"])
    c = assistant(preference=3, enabled=False)
    module = importlib.import_module("core.migrations.0037_ai_priority")
    module.migrate_priorities(apps, SimpleNamespace(connection=connection))
    assert list(AIConnection.objects.order_by("preference", "pk").values_list("pk", flat=True)) == [b.pk, a.pk, c.pk]
    assert not AIConnection.objects.filter(is_default=True).exists()
    b.refresh_from_db()
    assert b.roles == ["verifier"] and b.identity_id


def test_only_priority_controls_automatic_selection():
    stale = assistant(preference=100, is_default=True)
    first = assistant(preference=10)
    tied = assistant(preference=10)
    assert [item.pk for item in candidates()] == [first.pk, tied.pk, stale.pk]


@pytest.mark.parametrize("availability", ["QUOTA_EXHAUSTED", "BUSY", "UNAVAILABLE"])
def test_temporary_unavailability_does_not_remove_configured_roles(availability):
    item = assistant(availability=availability)
    item.identity.availability = availability
    item.identity.save()
    value = role_coverage()
    assert value["complete"] is True
    assert all(status == {"configured": [item.pk], "available": []} for status in value["roles"].values())


def test_coverage_combines_connections_and_excludes_disabled_or_disconnected():
    analyst = assistant(roles=["analyst"])
    assistant(roles=["counter_analyst"], enabled=False)
    disconnected = assistant(roles=["verifier"])
    disconnected.identity.status = "DISCONNECTED"
    disconnected.identity.save()
    value = role_coverage()
    assert value["complete"] is False
    assert value["roles"]["analyst"]["configured"] == [analyst.pk]
    assert not value["roles"]["counter_analyst"]["configured"]
    assistant(roles=["counter_analyst", "verifier"])
    assert role_coverage()["complete"] is True


def test_missing_roles_block_before_scope_inference_or_job_creation(environment):
    AIConnection.objects.update(roles=["analyst"])
    request = Request.objects.create(environment=environment, need="Explain exports")
    with patch("core.scope_service.assess") as assess:
        with pytest.raises(HttpError, match="AI role configuration is incomplete"):
            enqueue_analysis(request.pk, analysis_protocol="2.4")
    assess.assert_not_called()
    request.refresh_from_db()
    assert request.status == "DRAFT" and not Job.objects.exists()


def test_covered_but_exhausted_configuration_can_queue(environment):
    AIConnection.objects.all().delete()
    assistant(availability="QUOTA_EXHAUSTED")
    request = Request.objects.create(environment=environment, need="Explain exports")
    with patch("core.scope_service.assess", return_value=True):
        queued = enqueue_analysis(request.pk, analysis_protocol="2.4")
    assert queued.status == "QUEUED"
    assert Job.objects.filter(target=str(request.pk), status="QUEUED").exists()


def test_incomplete_configuration_can_be_saved(client):
    item = assistant()
    response = client.put(f"/api/ai-connections/{item.pk}", data='{"roles": [], "enabled": false}', content_type="application/json")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
