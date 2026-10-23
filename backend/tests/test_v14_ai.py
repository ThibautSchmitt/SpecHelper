import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.agent import ProviderUnavailable
from core.models import AIConnection, AIIdentity, AISession, Job, Request
from core.providers import (
    bind_session,
    candidates,
    mark_failure,
    normalize_quota_windows,
    observe,
    public,
    record_quota,
    refresh_unknown_connections,
    reserve_for_job,
)
from core.services import enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


def configuration(name, agent="codex", model="accepted-model", identity=None, **values):
    identity = identity or AIIdentity.objects.create(
        agent=agent, credential_id=uuid.uuid4(), status="CONNECTED", availability="AVAILABLE"
    )
    return AIConnection.objects.create(
        name=name,
        agent=agent,
        model=model,
        identity=identity,
        status="CONNECTED",
        availability="AVAILABLE",
        **values,
    )


def test_n_configurations_share_identity_quota_and_default_order():
    first = configuration("First", preference=20)
    second = configuration(
        "Same account, different model", model="other-model", identity=first.identity
    )
    preferred = configuration("Preferred", agent="claude", is_default=True)
    assert [item.pk for item in candidates()] == [preferred.pk, first.pk, second.pk]
    mark_failure(first.pk, "QUOTA_EXHAUSTED")
    assert [item.pk for item in candidates()] == [preferred.pk]
    assert public(first)["quota_identity_id"] == public(second)["quota_identity_id"]
    assert public(second)["availability"] == "QUOTA_EXHAUSTED"
    assert public(preferred)["quota_windows"] == {}
    assert public(preferred)["usage"] == "UNKNOWN"


def test_separate_logins_reliable_account_key_share_quota_and_capacity(environment):
    first, second = configuration("First"), configuration("Same actual account")
    for item in (first, second):
        observe(item, {"status": "CONNECTED", "account_key": "a" * 64})
    assert public(first)["quota_identity_id"] == public(second)["quota_identity_id"]
    request = Request.objects.create(
        environment=environment, need="Read sources", confrontation=True
    )
    job = Job.objects.create(kind="analysis", target=str(request.pk))
    AIConnection.objects.filter(pk=1).update(enabled=False)
    assert reserve_for_job(job)
    # Confronted requests reserve a connection at each public role boundary.
    from core.models import AnalysisRun
    from core.orchestration import assign_role
    from core.orchestration_settings import get_config

    run = AnalysisRun.objects.create(
        request=request,
        job=job,
        number=1,
        orchestration={"version": "1.5", "config": get_config(), "sessions": {}},
    )
    assign_role(request, run, "analyst")
    job.refresh_from_db()
    assert len(job.payload["connection_ids"]) == 1
    assert not candidates()
    assert request.ai_sessions.count() == 1
    assert request.ai_sessions.get().public_role == "analyst"


def test_health_does_not_reset_exhausted_quota_and_reliable_reset_can_recover():
    AIConnection.objects.all().update(enabled=False)
    item = configuration("Limited")
    mark_failure(item.pk, "QUOTA_EXHAUSTED")
    observe(item, {"status": "CONNECTED", "account": "Official account"})
    item.refresh_from_db()
    assert public(item)["availability"] == "QUOTA_EXHAUSTED"
    with patch("core.providers.observe") as observation:
        refresh_unknown_connections(lambda path: {"status": "CONNECTED"})
    observation.assert_not_called()
    AIIdentity.objects.filter(pk=item.identity_id).update(
        quota_windows={
            "weekly": {
                "exhausted": True,
                "resets_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            }
        },
        checked_at=None,
    )
    refresh_unknown_connections(lambda path: {"status": "CONNECTED"})
    assert candidates()[0].pk == item.pk


def test_model_or_identity_change_never_reuses_old_cli_context(environment):
    item = configuration("Research")
    request = Request.objects.create(environment=environment, need="Analyze")
    old = bind_session(request, item)
    old.runtime_id = str(uuid.uuid4())
    old.save()
    item.model = "different-model"
    item.save()
    new = bind_session(request, item)
    assert new.pk != old.pk
    assert new.context_id != old.context_id
    assert not new.runtime_id
    old.refresh_from_db()
    assert old.model_snapshot == "accepted-model"
    assert old.connection_name_snapshot == "Research"
    assert bind_session(request, item).pk == new.pk


def test_same_provider_n_fallbacks_are_bounded_and_audited(
    environment, storage, bundle, code_report
):
    AIConnection.objects.all().update(enabled=False)
    items = [configuration(f"Codex {index}", preference=index) for index in range(3)]
    request = Request.objects.create(environment=environment, need="Export")
    enqueue_analysis(request.pk)
    sid = str(uuid.uuid4())
    answers = [
        ProviderUnavailable("QUOTA_EXHAUSTED"),
        ProviderUnavailable("AUTH_ERROR"),
        {
            "session_id": sid,
            "model": "accepted-model",
            "output": {
                "status": "READY_TO_ANALYZE",
                "understanding": "Export",
                "questions": [],
                "ticket": None,
                "complexity": "simple",
            },
        },
        {"session_id": sid, "output": {"analysis": code_report, "result": bundle.model_dump()}},
    ]
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=answers) as caller,
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY", request.error
    assert [call.args[1]["identity_id"] for call in caller.call_args_list] == [
        str(items[0].identity.credential_id),
        str(items[1].identity.credential_id),
        str(items[2].identity.credential_id),
        str(items[2].identity.credential_id),
    ]
    steps = request.analysis_runs.get().steps
    assert [step.get("failure") for step in steps[:2]] == ["QUOTA_EXHAUSTED", "AUTH_ERROR"]
    assert steps[2]["connection_name"] == "Codex 2"
    assert steps[2]["model"] == "accepted-model"
    assert (
        len(set(AISession.objects.filter(request=request).values_list("context_id", flat=True)))
        == 3
    )


def test_all_configurations_unavailable_keeps_original_job_queued(environment, storage):
    AIConnection.objects.all().update(enabled=False)
    configuration("First")
    configuration("Second")
    request = Request.objects.create(environment=environment, need="Export")
    enqueue_analysis(request.pk)
    job = claim_job()
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call", side_effect=ProviderUnavailable("QUOTA_EXHAUSTED")
        ) as caller,
    ):
        perform_job(job)
    job.refresh_from_db()
    request.refresh_from_db()
    assert caller.call_count == 2
    assert job.status == request.status == "QUEUED"
    assert Job.objects.filter(target=str(request.pk)).count() == 1
    assert claim_job() is None


def test_configuration_added_after_fallback_budget_does_not_falsely_complete_job(
    environment, storage
):
    AIConnection.objects.all().update(enabled=False)
    configuration("First")
    request = Request.objects.create(environment=environment, need="Export")
    enqueue_analysis(request.pk)
    job = claim_job()
    created = []

    def caller(*args, **kwargs):
        created.append(configuration("Added during invocation"))
        raise ProviderUnavailable("QUOTA_EXHAUSTED")

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=caller) as runtime,
    ):
        perform_job(job)
    job.refresh_from_db()
    request.refresh_from_db()
    assert runtime.call_count == 1
    assert job.status == request.status == "QUEUED"
    assert created[0].pk in [value.pk for value in candidates()]
    assert not request.versions.exists()
    next_claim = claim_job()
    assert next_claim.pk == job.pk
    assert next_claim.payload["connection_ids"] == [created[0].pk]


def test_invalid_model_has_actionable_diagnostic_without_silent_substitution(environment, storage):
    AIConnection.objects.all().update(enabled=False)
    value = configuration("Unsupported", model="not-a-model")
    request = Request.objects.create(environment=environment, need="Export")
    enqueue_analysis(request.pk)
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call", side_effect=ProviderUnavailable("MODEL_UNAVAILABLE")
        ) as caller,
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "QUEUED"
    assert "selected model is unavailable" in Job.objects.get(target=str(request.pk)).error
    assert caller.call_count == 1
    observe(value, {"status": "CONNECTED"})
    value.refresh_from_db()
    assert value.availability == "MODEL_UNAVAILABLE"
    assert not candidates()


def test_config_crud_multiple_same_provider_and_shared_identity(client):
    from core.models import AIModel

    for agent, identifier in (("codex", "model-a"), ("codex", "model-b"), ("claude", "model-a")):
        AIModel.objects.create(agent=agent, identifier=identifier, name=identifier)
    def create(**values):
        response = client.post(
            "/api/ai-connections",
            data=json.dumps(
                {"name": "My assistant", "agent": "codex", "model": "model-a", **values}
            ),
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        return response.json()

    first = create(is_default=True)
    second = create(share_identity_from=first["id"], model="model-b")
    third = create(agent="claude", is_default=True)
    assert first["identity_id"] == second["identity_id"] != third["identity_id"]
    assert sum(item["is_default"] for item in client.get("/api/ai-connections").json()) == 1
    assert "credential_id" not in first
    assert client.delete(f"/api/ai-connections/{second['id']}").status_code == 200
    assert not AIConnection.objects.filter(pk=second["id"]).exists()


def test_shared_account_capacity_and_quota_do_not_reenable_a_rejected_model(environment):
    from core.providers import release_connections

    AIConnection.objects.all().update(enabled=False)
    valid = configuration("Valid model")
    invalid = configuration("Rejected model", identity=valid.identity, model="rejected")
    AIConnection.objects.filter(pk=invalid.pk).update(availability="MODEL_UNAVAILABLE")
    request = Request.objects.create(environment=environment, need="Keep rejected model excluded")
    job = Job.objects.create(kind="analysis", target=str(request.pk))
    assert reserve_for_job(job)
    release_connections([valid.pk])
    invalid.refresh_from_db()
    assert invalid.availability == "MODEL_UNAVAILABLE"
    mark_failure(
        valid.pk,
        "QUOTA_EXHAUSTED",
        quota_windows={
            "session": {
                "exhausted": True,
                "resets_at": (timezone.now() - timedelta(seconds=1)).isoformat(),
            }
        },
    )
    refresh_unknown_connections(lambda path: {"status": "CONNECTED"})
    invalid.refresh_from_db()
    assert invalid.availability == "MODEL_UNAVAILABLE"
    assert [item.pk for item in candidates()] == [valid.pk]


def test_history_protects_config_delete_and_preserves_model_snapshot(client, environment):
    from core.models import AIModel

    AIModel.objects.create(agent="codex", identifier="new-model", name="New model")
    value = configuration("Audit")
    request = Request.objects.create(environment=environment, need="Analyze")
    session = bind_session(request, value)
    assert client.delete(f"/api/ai-connections/{value.pk}").status_code == 409
    response = client.put(
        f"/api/ai-connections/{value.pk}",
        data=json.dumps({"enabled": False, "model": "new-model"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    session.refresh_from_db()
    assert session.model_snapshot == "accepted-model"


def test_targeted_auth_does_not_replace_other_same_provider_identity(client):
    first, second = configuration("One"), configuration("Two")
    with patch("core.connections.runtime_call", return_value={"status": "AWAITING_USER"}) as caller:
        response = client.post(f"/api/ai-connections/{second.pk}/auth/start")
    assert response.status_code == 200
    assert caller.call_args.args[1]["identity_id"] == str(second.identity.credential_id)
    with patch(
        "core.connections.runtime_call",
        return_value={"status": "CONNECTED", "account": "Second account"},
    ):
        client.get(f"/api/connections/attempts/{response.json()['id']}")
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.account == ""
    assert second.account == "Second account"


def test_observed_windows_are_normalized_and_shared_without_fabricated_values():
    item = configuration("Observed")
    shared = configuration("Shared", identity=item.identity)
    reset = (timezone.now() + timedelta(hours=2)).isoformat()
    record_quota(
        item,
        {
            "session": {
                "used_percent": 25,
                "resets_at": reset,
                "private_provider_field": "discard",
            },
            "weekly": {"used_percent": 100},
            "unknown_window": {"used_percent": 50},
        },
    )
    observed_windows = public(shared)["quota_windows"]
    assert all(window.get("observed_at") for window in observed_windows.values())
    assert {
        name: {key: value for key, value in window.items() if key != "observed_at"}
        for name, window in observed_windows.items()
    } == {
        "session": {"used_percent": 25, "exhausted": False, "resets_at": reset},
        "weekly": {"used_percent": 100, "exhausted": True},
    }
    assert public(shared)["availability"] == "QUOTA_EXHAUSTED"
    assert not candidates()
    assert (
        normalize_quota_windows(
            {
                "weekly": {"used_percent": float("inf")},
                "session": {"used_percent": True, "resets_at": "tomorrow"},
            }
        )
        == {}
    )
