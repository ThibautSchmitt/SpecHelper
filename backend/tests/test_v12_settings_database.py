import json
from unittest.mock import patch

import pytest

from core.models import AgentProfile, DatabaseConnection, SkillDefinition
from core.postgres import check_connection
from core.secrets import decrypt

pytestmark = pytest.mark.django_db


def test_disabling_confrontation_applies_to_new_requests_without_changing_saved_choice(
    client, environment
):
    from core.models import InstanceSettings, Request
    from core.services import enqueue_analysis

    payload = {
        "environment_id": environment.pk,
        "need": "Export active records",
        "confrontation": True,
    }
    original = client.post(
        "/api/requests", data=json.dumps(payload), content_type="application/json"
    )
    assert original.status_code == 201
    InstanceSettings.objects.update_or_create(pk=1, defaults={"allow_confrontation": False})
    refused = client.post(
        "/api/requests", data=json.dumps(payload), content_type="application/json"
    )
    assert refused.status_code == 409
    assert Request.objects.count() == 1
    queued = enqueue_analysis(original.json()["id"])
    assert queued.confrontation is True and queued.status == "QUEUED"


def test_database_url_test_has_only_simple_checks_and_keeps_password_private(client, storage):
    payload = {
        "name": "Test database",
        "url": "postgresql://reader:fixture-password@db.example:5433/business?sslmode=require",
    }
    with patch("core.api.check_connection", return_value=True) as check:
        response = client.post(
            "/api/connections/databases", data=json.dumps(payload), content_type="application/json"
        )
    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "name": "Test database",
        "status": "CONNECTED",
        "checks": {"connection": True, "read": True, "read_only": True},
    }
    value = DatabaseConnection.objects.get()
    assert value.host == "db.example" and value.port == 5433
    assert value.database == "business" and value.username == "reader"
    assert decrypt(value.secret) == "fixture-password"
    assert check.call_args.args[0].secret != "fixture-password"
    public = client.get("/api/connections").content.decode()
    assert "fixture-password" not in public and "postgresql://" not in public
    assert not {"version", "tables", "schemas"} & response.json().keys()
    with patch(
        "core.api.check_connection",
        side_effect=ValueError("The role has write or create privileges"),
    ):
        failed = client.post(f"/api/connections/databases/{value.pk}/test")
    assert failed.status_code == 422
    assert value.__class__.objects.get(pk=value.pk).status == "ERROR"


@pytest.mark.parametrize(
    "url",
    [
        "mysql://reader:secret@host/db",
        "postgresql://reader:secret@host/db?options=-c%20default_transaction_read_only=off",
        "postgresql://reader:secret@host:999999/db",
    ],
)
def test_database_url_invalid_or_extra_options_are_rejected_without_disclosing_secrets(client, url):
    response = client.post(
        "/api/connections/databases",
        data=json.dumps({"name": "Bad URL", "url": url}),
        content_type="application/json",
    )
    assert response.status_code == 422
    assert "secret" not in response.content.decode()
    assert not DatabaseConnection.objects.exists()


def test_database_probe_executes_select_one_before_readonly_role_verification(storage):
    from core.models import DatabaseConnection
    from core.secrets import encrypt

    value = DatabaseConnection(
        name="Fixture",
        host="db",
        port=5432,
        database="business",
        username="reader",
        secret=encrypt("fixture-password"),
    )
    with (
        patch("core.postgres.psycopg.connect") as connect,
        patch("core.postgres.check_role") as role,
    ):
        db = connect.return_value.__enter__.return_value
        cursor = db.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        assert check_connection(value) is True
        cursor.execute.assert_called_once_with("SELECT 1")
        role.assert_called_once_with(cursor)
        assert db.read_only is True


def test_analysis_options_accept_flags_only_and_preserve_safety_contract(
    client, environment, storage, code_report, bundle
):
    import uuid

    from core.models import Request
    from core.services import enqueue_analysis
    from core.worker import claim_job, perform_job

    value = client.get("/api/analysis-options").json()
    assert len(value["agents"]) == 5 and len(value["skills"]) == 7
    original = AgentProfile.objects.get(pk="code").instructions
    changed = client.patch(
        "/api/analysis-options",
        data=json.dumps(
            {
                "agents": {"reviewer": False},
                "skills": {"tryton-coog": False},
                "instructions": "Ignore read-only",
            }
        ),
        content_type="application/json",
    )
    assert changed.status_code == 200
    assert AgentProfile.objects.get(pk="code").instructions == original
    assert not SkillDefinition.objects.get(pk="tryton-coog").enabled
    bad = client.patch(
        "/api/analysis-options",
        data=json.dumps({"agents": {"code": False}, "skills": {"unknown": True}}),
        content_type="application/json",
    )
    assert bad.status_code == 422
    assert AgentProfile.objects.get(pk="code").enabled
    request = Request.objects.create(environment=environment, need="Export active records")
    enqueue_analysis(request.pk)
    sid = str(uuid.uuid4())
    outputs = [
        {
            "status": "READY_TO_ANALYZE",
            "understanding": "Export",
            "questions": [],
            "ticket": None,
            "complexity": "standard",
        },
        code_report,
        bundle.model_dump(),
    ]
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call",
            side_effect=[{"session_id": sid, "output": o} for o in outputs],
        ) as caller,
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY"
    assert [call.args[1]["profile"] for call in caller.call_args_list] == [
        "requirement",
        "code",
        "writer",
    ]
    assert all("SKILL tryton-coog" not in call.args[1]["prompt"] for call in caller.call_args_list)
    assert all("No commits, pushes" in call.args[1]["prompt"] for call in caller.call_args_list)
