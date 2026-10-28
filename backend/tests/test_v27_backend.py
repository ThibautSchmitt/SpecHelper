"""Native-provider registration, shared scheduling and service-enforced permission limits."""

import copy
import importlib.util
import io
import json
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.agent import ProviderUnavailable, runtime_call
from core.ai_api import APIKeyAuthenticationIn
from core.global_skills import catalog
from core.library import DefinitionIn, save_definition
from core.model_catalog import list_catalog, record_execution
from core.models import (
    AIConnection,
    AIIdentity,
    AIModel,
    AnalysisRun,
    ConnectionAttempt,
    Job,
    LibraryRevision,
    Request,
    SkillDefinition,
)
from core.orchestration import RoleUnavailable, assign_role, family, select_connection
from core.orchestration_settings import get_config
from core.permission_evidence import (
    PERMISSION_LIMIT,
    TOOL_ERROR_LIMIT,
    observation,
    qualify_report,
    trace,
)
from core.providers import (
    candidates,
    mark_failure,
    observe,
    public,
    release_connections,
)
from core.services import enqueue_analysis
from core.step_execution import complete_invocation
from core.ticket_presentation import publication_blockers
from core.worker import claim_job, perform_job

SPEC = importlib.util.spec_from_file_location(
    "v27_omission_fixtures", Path(__file__).with_name("test_v24_omissions.py")
)
omissions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(omissions)
committed_source = omissions.committed_source

pytestmark = pytest.mark.django_db


def assistant(agent="antigravity", **values):
    identity = values.pop("identity", None) or AIIdentity.objects.create(
        agent=agent, credential_id=uuid.uuid4(), status="CONNECTED", availability="AVAILABLE"
    )
    return AIConnection.objects.create(
        agent=agent,
        name=agent + " fixture",
        identity=identity,
        status="CONNECTED",
        availability="AVAILABLE",
        **values,
    )


def post(client, path, value):
    return client.post(path, data=json.dumps(value), content_type="application/json")


def test_antigravity_connection_is_explicit_and_does_not_fabricate_models(client):
    response = post(client, "/api/ai-connections", {"name": "Research", "agent": "antigravity"})
    assert response.status_code == 200, response.content
    created = response.json()
    assert created["agent"] == "antigravity" and created["model"] == ""
    assert created["status"] == "UNKNOWN" and created["quota_windows"] == {}
    assert created["usage"] == "UNKNOWN"
    assert list_catalog(agent="antigravity")["items"] == []
    assert "credential_id" not in created
    assert AIConnection.objects.filter(agent="antigravity").count() == 1
    changed = client.put(
        f"/api/ai-connections/{created['id']}",
        data=json.dumps({"agent": "claude"}),
        content_type="application/json",
    )
    assert changed.status_code == 422


def test_metadata_discovery_preserves_exact_slugs_and_actual_family_without_entitlement(
    client, monkeypatch
):
    configured = assistant()
    slug = "gemini-fixture-high-preview.2026"
    calls = []

    def discover(path, **kwargs):
        calls.append(path)
        return {
            "state": "supported",
            "reason": "catalog_not_entitlement",
            "items": [{"identifier": slug, "name": "Observed label", "family": "google"}],
        }

    monkeypatch.setattr("core.model_catalog.runtime_call", discover)
    response = client.post(f"/api/ai-connections/{configured.pk}/models/refresh")
    assert response.status_code == 200, response.content
    model = response.json()["items"][0]
    assert model["identifier"] == slug and model["family"] == "google"
    assert model["status"] == "SUPPORTED" and model["source"] == "adapter"
    assert calls == [
        f"/models?agent=antigravity&identity_id={configured.identity.credential_id}"
    ]
    record_execution(configured, slug, True)
    assert list_catalog(connection=configured)["items"][0]["status"] == "AVAILABLE"
    assert client.post(f"/api/ai-connections/{configured.pk}/models/refresh").json()["items"][0][
        "status"
    ] == "AVAILABLE"


def test_unknown_model_selection_never_substitutes_a_catalog_entry(client):
    AIModel.objects.create(agent="antigravity", identifier="exact-observed", name="Observed")
    response = post(
        client, "/api/ai-connections",
        {"name": "Pinned", "agent": "antigravity", "model": "not-observed"},
    )
    assert response.status_code == 422
    assert not AIConnection.objects.filter(name="Pinned").exists()
    accepted = post(
        client, "/api/ai-connections",
        {"name": "Pinned", "agent": "antigravity", "model": "exact-observed"},
    )
    assert accepted.status_code == 422
    assert not AIConnection.objects.filter(name="Pinned").exists()


def test_antigravity_auth_uses_only_the_selected_identity_and_retains_provider_label(
    client, monkeypatch
):
    first, second = assistant(), assistant()
    calls = []

    def start(path, payload=None, **kwargs):
        calls.append((path, payload))
        return {"status": "AWAITING_USER", "input_required": True}

    monkeypatch.setattr("core.connections.runtime_call", start)
    response = client.post(f"/api/ai-connections/{second.pk}/auth/start")
    assert response.status_code == 200, response.content
    attempt = response.json()["id"]
    assert calls[0][0] == "/auth/start"
    assert calls[0][1]["identity_id"] == str(second.identity.credential_id)
    assert calls[0][1]["provider"] == "antigravity"
    monkeypatch.setattr(
        "core.connections.runtime_call", lambda *args, **kwargs: {"status": "CONNECTED"}
    )
    assert client.get(f"/api/connections/attempts/{attempt}").status_code == 200
    second.refresh_from_db()
    first.refresh_from_db()
    assert second.account == "Antigravity" and first.account == ""


def test_explicit_api_key_requires_billing_consent_and_never_persists_or_echoes_the_key(
    client, monkeypatch, caplog
):
    configured = assistant()
    secret = "fixture-only-antigravity-key-never-persist"
    calls = []

    def configure(path, payload, **kwargs):
        calls.append((path, copy.deepcopy(payload)))
        return {"status": "CONNECTED", "account": "API key configured " + secret}

    monkeypatch.setattr("core.ai_api.runtime_call", configure)
    path = f"/api/ai-connections/{configured.pk}/auth/api-key"
    assert post(client, path, {"api_key": secret}).status_code == 422
    assert post(client, path, {"api_key": secret, "confirm_billing": False}).status_code == 422
    for invalid_consent in (1, "true", None):
        invalid = post(client, path, {"api_key": secret, "confirm_billing": invalid_consent})
        assert invalid.status_code == 422 and secret not in invalid.content.decode()
    assert calls == []
    result = post(client, path, {"api_key": secret, "confirm_billing": True})
    assert result.status_code == 200, result.content
    assert result.json()["authentication_mode"] == "api_key"
    assert result.json()["access_verified"] is False
    assert secret not in result.content.decode() and secret not in caplog.text
    assert calls == [
        ("/auth/api-key", {
            "provider": "antigravity",
            "identity_id": str(configured.identity.credential_id),
            "api_key": secret,
            "confirm_billing": True,
        })
    ]
    assert secret not in str(list(AIIdentity.objects.values()))
    assert secret not in str(list(AIConnection.objects.values()))
    assert not ConnectionAttempt.objects.exists() and not Job.objects.exists()
    assert secret not in repr(APIKeyAuthenticationIn(api_key=secret, confirm_billing=True))


def test_api_key_setup_is_provider_scoped_and_refuses_busy_shared_accounts(client, monkeypatch):
    key = {"api_key": "fixture-only-explicit-key", "confirm_billing": True}
    monkeypatch.setattr(
        "core.ai_api.runtime_call", lambda *a, **k: pytest.fail("No credential mutation allowed")
    )
    other = assistant("codex")
    assert post(client, f"/api/ai-connections/{other.pk}/auth/api-key", key).status_code == 422
    configured = assistant()
    shared = assistant(identity=configured.identity)
    AIIdentity.objects.filter(pk=configured.identity_id).update(availability="BUSY")
    assert post(client, f"/api/ai-connections/{shared.pk}/auth/api-key", key).status_code == 409


@pytest.mark.parametrize("bad_key", ["too-short", "invalid-key\nwith-newline", "x" * 257])
def test_api_key_validation_rejects_unsafe_values_without_echo(client, monkeypatch, bad_key):
    configured = assistant()
    monkeypatch.setattr(
        "core.ai_api.runtime_call", lambda *a, **k: pytest.fail("Invalid key must not reach vault")
    )
    response = post(client, f"/api/ai-connections/{configured.pk}/auth/api-key", {
        "api_key": bad_key, "confirm_billing": True,
    })
    assert response.status_code == 422
    assert bad_key not in response.content.decode()


def test_antigravity_quota_is_unknown_and_authentication_does_not_clear_known_exhaustion():
    configured = assistant()
    value = observe(configured, {
        "status": "CONNECTED", "account": "Antigravity",
        "quota_status": {"state": "unavailable", "reason": "unsupported_cli"},
    })
    assert value["quota_windows"] == {}
    assert value["quota_status"]["source"] == "antigravity_cli"
    assert value["usage"] == value["reset"] == "UNKNOWN"
    mark_failure(configured.pk, "QUOTA_EXHAUSTED")
    value = observe(configured, {"status": "CONNECTED"})
    assert value["availability"] == "QUOTA_EXHAUSTED"
    assert configured.pk not in [c.pk for c in candidates()]


@pytest.mark.parametrize("windows", [
    {},
    {"_status": {"state": "unavailable", "reason": "unsupported_cli"}},
    {"session": {"used_percent": 1, "exhausted": False}},
])
def test_periodic_refresh_cannot_infer_quota_recovery_from_missing_or_low_usage(windows):
    from core.providers import refresh_unknown_connections

    configured = assistant()
    AIConnection.objects.exclude(pk=configured.pk).update(enabled=False)
    mark_failure(configured.pk, "QUOTA_EXHAUSTED")
    AIIdentity.objects.filter(pk=configured.identity_id).update(quota_windows=windows, checked_at=None)
    caller = Mock(return_value={"status": "CONNECTED"})
    refresh_unknown_connections(caller)
    caller.assert_not_called()
    assert public(configured)["availability"] == "QUOTA_EXHAUSTED"
    assert configured.pk not in [connection.pk for connection in candidates()]


def test_configured_key_metadata_cannot_clear_an_actual_authentication_rejection():
    configured = assistant()
    AIIdentity.objects.filter(pk=configured.identity_id).update(account_key="a" * 64)
    mark_failure(configured.pk, "AUTH_ERROR")
    unchanged = observe(configured, {
        "status": "CONNECTED", "account_key": "a" * 64, "access_verified": False,
        "authentication_mode": "api_key",
    })
    assert unchanged["status"] == "DISCONNECTED"
    assert unchanged["availability"] == "AUTH_ERROR"
    assert configured.pk not in [item.pk for item in candidates()]
    changed = observe(configured, {
        "status": "CONNECTED", "account_key": "b" * 64, "access_verified": False,
        "authentication_mode": "api_key",
    })
    assert changed["status"] == "CONNECTED"
    assert configured.pk in [item.pk for item in candidates()]


def test_three_actual_provider_families_use_isolated_role_contexts(environment):
    AIConnection.objects.all().update(enabled=False)
    items = [
        assistant("codex", roles=["analyst"]),
        assistant("claude", roles=["counter_analyst"]),
        assistant("antigravity", roles=["verifier"]),
    ]
    request = Request.objects.create(
        environment=environment, need="Explain actual source behavior.", analysis_protocol="2.4"
    )
    job = Job.objects.create(kind="analysis", target=str(request.pk))
    run = AnalysisRun.objects.create(
        request=request, number=1, job=job,
        orchestration={"version": "2.4", "config": get_config(), "sessions": {}},
    )
    sessions = [assign_role(request, run, role) for role in ("analyst", "counter_analyst", "verifier")]
    assert [s.connection_id for s in sessions] == [item.pk for item in items]
    assert [s.family_snapshot for s in sessions] == ["openai", "anthropic", "google"]
    assert len({s.context_id for s in sessions}) == 3
    assert all(not s.runtime_id for s in sessions)
    assert all(s.identity_snapshot == item.identity_id for s, item in zip(sessions, items, strict=True))


def test_actual_model_family_and_forbidden_roles_cannot_be_faked_by_provider_labels():
    configured = assistant(roles=["analyst"], model="observed-claude-model")
    AIModel.objects.create(
        agent="antigravity", identifier=configured.model, name="Provider label", family="anthropic"
    )
    assert family(configured) == "anthropic"
    with pytest.raises(RoleUnavailable):
        select_connection("verifier", get_config())


def test_full_worker_flow_runs_three_families_with_frozen_sources_and_independent_contexts(
    environment, storage, committed_source, bundle
):
    from core.models import InstanceSettings

    AIConnection.objects.all().update(enabled=False)
    first = assistant("codex", roles=["analyst"])
    second = assistant("claude", roles=["counter_analyst"])
    third = assistant(
        "antigravity", roles=["verifier"], model="fixture-observed-gemini",
        additional_instructions="ANTIGRAVITY_ROLE_MARKER: Keep source limits visible.",
    )
    AIModel.objects.create(
        agent="antigravity", identifier=third.model, name="Observed fixture", family="google"
    )
    settings, _ = InstanceSettings.objects.get_or_create(pk=1)
    settings.orchestration = {
        **settings.orchestration,
        "global_instructions": "GLOBAL_TRACE_MARKER: State evidence limits.",
    }
    settings.save(update_fields=["orchestration"])
    source = committed_source
    request = Request.objects.create(
        environment=environment, analysis_protocol="2.4", confrontation=True,
        need="Explain the cancellation guard and its migration exception.", language="en",
    )
    enqueue_analysis(request.pk)
    values = [
        {"status": "READY_TO_ANALYZE", "understanding": "Cancellation guard",
         "questions": [], "ticket": None, "complexity": "simple"},
        omissions.report(source),
        omissions.report(source, exception=True),
        {"status": "APPROVED", "summary": "Review the migration exception.",
         "issues": [], "verification": None},
        omissions.verification(source),
        bundle.model_dump(),
    ]
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(copy.deepcopy(payload))
        return {"output": values.pop(0), "session_id": str(uuid.uuid4()), "model": payload["model"]}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        for _ in range(10):
            job = claim_job()
            assert job is not None
            perform_job(job)
            request.refresh_from_db()
            if request.status in {"READY", "PARTIAL", "ERROR"}:
                break
    assert request.status == "READY", request.error
    assert not values and len(calls) == 6
    assert [call["agent"] for call in calls] == [
        "codex", "codex", "claude", "claude", "antigravity", "antigravity"
    ]
    assert [call["public_role"] for call in calls] == [
        "analyst", "analyst", "counter_analyst", "counter_analyst", "verifier", "verifier"
    ]
    assert len({call["context_id"] for call in calls}) == 6
    assert all(call["session_id"] is None and call["independent_context"] for call in calls)
    assert all(call["workspace"] == str(storage) and call["repositories"] == [
        "company/backend"
    ] for call in calls)
    assert all(source["commit"] in call["prompt"] for call in calls)
    assert all("GLOBAL_TRACE_MARKER" in call["prompt"] for call in calls)
    assert all("ANTIGRAVITY_ROLE_MARKER" in call["prompt"] for call in calls[-2:])
    assert all(call["model"] == third.model for call in calls[-2:])
    assert {call["identity_id"] for call in calls} == {
        str(item.identity.credential_id) for item in (first, second, third)
    }
    assert all(call["skill_definitions"] for call in calls)
    version = request.versions.get()
    assert not version.evidence["blocking"] and version.baseline[0]["sha"] == source["commit"]
    assert {step["model_family"] for step in request.analysis_runs.get().steps} == {
        "openai", "anthropic", "google"
    }


def test_shared_antigravity_account_reserves_one_step_and_preserves_other_waiting_job(
    environment
):
    AIConnection.objects.all().update(enabled=False)
    first = assistant()
    second = assistant(identity=first.identity)
    requests = [
        Request.objects.create(
            environment=environment, need=f"Inspect source behavior {index}.",
            analysis_protocol="2.4", confrontation=True,
        ) for index in range(2)
    ]
    for value in requests:
        enqueue_analysis(value.pk)
    claimed = claim_job()
    assert claimed.target == str(requests[0].pk)
    assert claim_job() is None
    assert Job.objects.get(target=str(requests[1].pk)).status == "QUEUED"
    assert not candidates()
    assert public(first)["quota_identity_id"] == public(second)["quota_identity_id"]
    complete_invocation(claimed, claimed.payload["attempt_id"])
    next_job = claim_job()
    assert next_job.target == str(requests[1].pk)
    release_connections(next_job.payload["connection_ids"])


def test_antigravity_global_skills_need_no_assignments_and_preserve_legacy_revisions():
    legacy = SkillDefinition.objects.create(
        slug="legacy-readable-v27", name="Legacy readable", objective="Inspect sources.",
        instructions="Read project sources and record limits.", compatibility=["codex"],
    )
    configured = assistant(additional_instructions="Keep business conditions explicit.")
    available = catalog(configured)
    value = next(row for row in available["definitions"] if row["slug"] == legacy.slug)
    assert value["compatibility"] == []
    assert LibraryRevision.objects.get(slug=legacy.slug, version=1).definition[
        "compatibility"
    ] == ["codex"]
    legacy.refresh_from_db()
    assert legacy.compatibility == ["codex"]
    saved = save_definition(
        "skill", DefinitionIn(
            slug="portable-v27", name="Portable review", objective="Inspect source boundaries.",
            instructions="Read project sources and state limits."
        ),
    )
    assert saved["compatibility"] == []
    assert any(row["slug"] == saved["slug"] for row in catalog(configured)["definitions"])


@pytest.mark.parametrize("workflow", ["request", "question"])
@pytest.mark.parametrize("denied_call", [1, 4, 5])
def test_permission_refusal_survives_a_ready_writer_and_blocks_publication(
    environment, storage, committed_source, bundle, workflow, denied_call
):
    source = committed_source
    value = Request.objects.create(
        environment=environment, analysis_protocol="2.4", workflow=workflow,
        need="Explain the actual cancellation conditions.", language="en",
    )
    enqueue_analysis(value.pk)
    final = bundle.model_dump() if workflow == "request" else {
        "status": "READY",
        "answer": {"title": "Cancellation", "summary": "Cancellation has conditions."},
    }
    outputs = [
        {"status": "READY_TO_ANALYZE", "understanding": "Cancellation",
         "questions": [], "ticket": None, "complexity": "simple"},
        omissions.report(source, workflow),
        omissions.report(source, workflow, True),
        {"status": "APPROVED", "summary": "Review scope.", "issues": [], "verification": None},
        omissions.verification(source),
        final,
    ]
    calls = []

    def invoke(path, payload, **kwargs):
        index = len(calls)
        calls.append(copy.deepcopy(payload))
        result = {
            "output": outputs.pop(0),
            "session_id": str(uuid.uuid4()),
            "permission_snapshot": {
                "mode": "request-review",
                "tools": ["view_file", "run_command", "private-unknown-tool"],
                "arguments": "private-native-init-fields",
            },
            "permission_grants": {
                "allow": ["command(git)", "command(curl)", "command(private-command)"],
                "deny": ["write_file(*)"],
            },
        }
        if index == denied_call:
            result.update(
                permission_limits=["provider-specific raw message must not persist"],
                permission_events=[{
                    "tool": "run_command", "status": "denied",
                    "arguments": "private-provider-tool-arguments",
                }],
                result_status="partial",
            )
        return result

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        for _ in range(10):
            job = claim_job()
            assert job is not None
            perform_job(job)
            value.refresh_from_db()
            if value.status in {"READY", "PARTIAL", "ERROR"}:
                break
    assert value.status == "PARTIAL", value.error
    version = value.versions.get()
    assert version.evidence["blocking"] and PERMISSION_LIMIT in version.evidence["limitations"]
    assert publication_blockers(version)
    run = value.analysis_runs.get()
    assert run.orchestration["permission_limits"] == [PERMISSION_LIMIT]
    assert "private-provider-tool-arguments" not in json.dumps(run.steps)
    assert "private-native-init-fields" not in json.dumps(run.steps)
    assert all(step["permission_snapshot"] == {
        "mode": "request-review", "tools": ["view_file", "run_command"]
    } for step in run.steps)
    assert all(step["permission_grants"] == {
        "allow": ["command(git)", "command(curl)"], "deny": ["write_file(*)"]
    } for step in run.steps)
    assert "provider-specific raw message" not in json.dumps(run.orchestration)
    assert any(row.get("permission_events") == [
        {"tool": "run_command", "status": "denied"}
    ] for row in run.steps)
    assert all(PERMISSION_LIMIT in artifact.content for artifact in version.artifacts.all())


def test_permission_observation_never_persists_arbitrary_tool_names_or_raw_messages():
    limits, events = observation({
        "permission_events": [
            {"tool": "private-string-that-is-not-a-known-tool", "status": "denied", "output": "secret"},
            {"tool": "view_file", "status": "allowed", "arguments": "secret"},
            {"tool": "run_command", "status": "unexpected", "output": "secret"},
        ]
    })
    assert limits == [PERMISSION_LIMIT]
    assert events == [
        {"tool": "unknown", "status": "denied"}, {"tool": "view_file", "status": "allowed"}
    ]


def test_permission_trace_keeps_native_observation_separate_from_service_grants():
    value = trace({
        "permission_snapshot": {
            "mode": "request-review", "tools": ["view_file", "run_command", "view_file"],
            "api_key": "private-native-metadata",
        },
        "permission_grants": {
            "allow": [
                "command(git)", "command(curl)", "command(rm)", "private-rule",
                "read_file(/workspace)", "read_file(/skills)", "read_file(/context)",
                "read_file(/attachments)", "read_file(/credentials)", "read_file(*)",
            ],
            "deny": ["write_file(*)", "private-rule"],
            "unsafe": "private-grant-field",
        },
    })
    assert value == {
        "permission_snapshot": {"mode": "request-review", "tools": ["view_file", "run_command"]},
        "permission_grants": {
            "allow": [
                "command(git)", "command(curl)", "read_file(/workspace)",
                "read_file(/skills)", "read_file(/context)", "read_file(/attachments)",
            ],
            "deny": ["write_file(*)"],
        },
    }
    assert trace({
        "permission_snapshot": {"mode": ["malformed"], "tools": [{}, "private-tool"]},
        "permission_grants": {"allow": [[], "command(git push)"]},
    }) == {"permission_snapshot": {"tools": []}, "permission_grants": {"allow": []}}
    assert observation({
        "permission_events": [{"tool": [], "status": "denied"}, {"status": []}]
    }) == ([PERMISSION_LIMIT], [{"tool": "unknown", "status": "denied"}])


def test_tool_failure_is_not_misrepresented_as_permission_denial():
    from core.analysis_evidence import ReliabilityReport

    limits, events = observation({
        "permission_limits": [TOOL_ERROR_LIMIT],
        "permission_events": [{"tool": "run_command", "status": "unknown"}],
    })
    assert limits == [TOOL_ERROR_LIMIT]
    assert events == [{"tool": "run_command", "status": "unknown"}]
    report = qualify_report(ReliabilityReport(claims=[]), limits)
    assert report.blocking and report.limitations == [TOOL_ERROR_LIMIT]
    assert observation({"result_status": "partial"}) == ([TOOL_ERROR_LIMIT], [])


@pytest.mark.parametrize("limit", [PERMISSION_LIMIT, TOOL_ERROR_LIMIT])
def test_service_permission_limits_follow_the_artifact_language(limit):
    from core.evidence_rendering import render_evidence
    from core.i18n import translate

    french = render_evidence({"claims": [], "limitations": [limit]}, "fr")
    assert translate(limit, "fr") in french and limit not in french
    assert limit in render_evidence({"claims": [], "limitations": [limit]}, "en")


def test_runtime_timeout_keeps_technical_status_and_permission_observations(settings):
    settings.RUNTIME_TOKEN = "fixture-control"
    value = {
        "timed_out": True, "failure": {"kind": "TIMEOUT"},
        "permission_grants": {"allow": ["command(git)"], "deny": ["write_file(*)"]},
        "permission_snapshot": {"mode": "request-review", "tools": ["view_file"]},
    }
    with patch("core.agent.httpx.Client") as client:
        response = client.return_value.__enter__.return_value.request.return_value
        response.status_code, response.json.return_value = 200, value
        assert runtime_call("/run", {}) == value


def test_permission_failure_keeps_safe_grants_through_provider_unavailable(settings):
    settings.RUNTIME_TOKEN = "fixture-control"
    context = {
        "usage": {"input_tokens": 40, "output_tokens": 2, "total_tokens": 42},
        "permission_grants": {"allow": ["command(git)"], "deny": ["write_file(*)"]},
        "permission_snapshot": {"mode": "request-review", "tools": ["view_file"]},
        "permission_limits": [PERMISSION_LIMIT],
    }
    with patch("core.agent.httpx.Client") as client:
        response = client.return_value.__enter__.return_value.request.return_value
        response.status_code = 200
        response.json.return_value = {"failure": {"kind": "PERMISSION_DENIED"}, **context}
        with pytest.raises(ProviderUnavailable) as caught:
            runtime_call("/run", {})
    assert caught.value.kind == "PERMISSION_DENIED"
    assert caught.value.context_observation == context


def test_unusable_permission_denial_is_explicit_error_without_false_capacity_wait(
    environment, storage
):
    request = Request.objects.create(
        environment=environment, need="Inspect actual source behavior.", analysis_protocol="2.4"
    )
    enqueue_analysis(request.pk)
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=ProviderUnavailable(
            "PERMISSION_DENIED", context_observation={
                "permission_limits": [PERMISSION_LIMIT],
                "usage": {"input_tokens": 40, "output_tokens": 2, "total_tokens": 42},
            }
        )),
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "ERROR" and "permission policy" in request.error
    assert not request.versions.exists()
    assert Job.objects.get(target=str(request.pk)).status == "ERROR"
    assert request.analysis_runs.get().steps[-1]["usage"]["total_tokens"] == 42


def test_metadata_control_relay_allows_only_scoped_reads_not_run_or_arbitrary_targets(
    settings, monkeypatch
):
    from core.gateway import Handler

    settings.RUNTIME_TOKEN = "fixture-control"
    calls = []
    monkeypatch.setattr(
        "core.gateway.runtime_call", lambda path, *a, **k: calls.append(path) or {"items": []}
    )

    def request(path):
        handler = object.__new__(Handler)
        handler.command, handler.path = "GET", path
        handler.headers = {"Authorization": "Bearer fixture-control"}
        handler.rfile = io.BytesIO()
        responses = []
        handler.respond = lambda code, payload: responses.append((code, payload))
        handler.dispatch()
        return responses[0]

    identity = str(uuid.uuid4())
    assert request(f"/models?agent=antigravity&identity_id={identity}")[0] == 200
    assert calls == [f"/models?agent=antigravity&identity_id={identity}"]
    assert request("/run?agent=antigravity")[0] == 404
    assert request("/models?agent=unknown")[0] == 422
    assert request("/models?agent=antigravity&identity_id=invalid")[0] == 422
    assert len(calls) == 1
