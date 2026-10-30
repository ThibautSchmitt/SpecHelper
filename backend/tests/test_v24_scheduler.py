"""Real PostgreSQL leases, overlapping jobs and fenced checkpoint recovery."""

import copy
import importlib.util
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection, connections
from django.utils import timezone

from core.analysis_flow import RequirementAssessment
from core.git import run as git
from core.models import (
    AIConnection,
    AIIdentity,
    AnalysisRun,
    Environment,
    EnvironmentRepository,
    Job,
    Request,
    StepExecution,
)
from core.results import publish
from core.services import enqueue_analysis
from core.step_execution import (
    ExecutionStopped,
    acknowledge_cancellation,
    cancel_request,
    complete_invocation,
    recover_steps,
)
from core.worker import claim_job, perform_job, recover_stale_jobs

pytestmark = pytest.mark.django_db(transaction=True)

SPEC = importlib.util.spec_from_file_location(
    "v24_omission_test_data", Path(__file__).with_name("test_v24_omissions.py")
)
omissions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(omissions)


@pytest.fixture(autouse=True)
def postgres_locking_required():
    if connection.vendor != "postgresql":
        pytest.skip("These scheduler integration checks require real PostgreSQL row locks")


def ready():
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Explain cancellation boundaries.",
        "questions": [],
        "ticket": None,
        "complexity": "simple",
    }


def response(payload, output=None):
    return {"output": output or ready(), "session_id": payload["session_id"] or str(uuid.uuid4())}


@pytest.fixture
def prepared(environment, storage, settings):
    # Retain the explicitly serialized deployment profile in historical lease tests.
    settings.AI_ACCOUNT_CONCURRENCY = 1
    AIConnection.objects.exclude(pk=1).update(enabled=False)
    identity = AIIdentity.objects.create(
        agent="codex", credential_id=uuid.uuid4(), status="CONNECTED", availability="AVAILABLE"
    )
    AIConnection.objects.filter(pk=1).update(identity=identity, enabled=True)
    repository = storage / "company/backend"
    repository.mkdir(parents=True)
    (repository / "policy.py").write_text(omissions.SOURCE)
    git("init", repository)
    git("-C", repository, "add", "policy.py")
    git(
        "-C",
        repository,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    source = omissions.synthetic_source()
    source["commit"] = git("-C", repository, "rev-parse", "HEAD")
    environment.repositories.update(sha=source["commit"])
    return environment, storage, source


def assistant(agent="claude", roles=None, account_key=""):
    identity = AIIdentity.objects.create(
        agent=agent,
        credential_id=uuid.uuid4(),
        account_key=account_key,
        status="CONNECTED",
        availability="AVAILABLE",
    )
    return AIConnection.objects.create(
        agent=agent,
        name=agent + " fixture",
        roles=roles or ["analyst", "counter_analyst", "verifier"],
        identity=identity,
        status="CONNECTED",
        availability="AVAILABLE",
    )


def start(environment, need="Explain cancellation boundaries."):
    request = Request.objects.create(
        environment=environment, analysis_protocol="2.4", need=need, language="en"
    )
    enqueue_analysis(request.pk)
    return request, Job.objects.get(kind="analysis", target=str(request.pk))


def in_thread(operation):
    """Each competing worker uses an independent PostgreSQL connection."""
    close_old_connections()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '3s'")
            cursor.execute("SET statement_timeout = '8s'")
        return operation()
    finally:
        connections.close_all()


def invoke(job, storage, output=None):
    calls = []

    def controlled(path, payload, **kwargs):
        assert path == "/run"
        calls.append(copy.deepcopy(payload))
        return response(payload, output)

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=controlled),
    ):
        perform_job(job)
    return calls


@pytest.mark.parametrize("shared_account", [False, True])
def test_two_jobs_really_overlap_on_compatible_accounts(prepared, settings, shared_account):
    environment, storage, source = prepared
    if shared_account:
        settings.AI_ACCOUNT_CONCURRENCY = 2
    else:
        assistant()
    environment.context_instructions = "FIRST_ENVIRONMENT_FACTS_ONLY"
    environment.save(update_fields=["context_instructions"])
    other_environment = Environment.objects.create(
        name="Other isolated environment",
        status="READY",
        context_instructions="SECOND_ENVIRONMENT_FACTS_ONLY",
    )
    EnvironmentRepository.objects.create(
        environment=other_environment,
        repository="company/backend",
        branch="main",
        sha=source["commit"],
    )
    first, first_job = start(environment, "Explain the application: FIRST_JOB_FACTS_ONLY")
    second, second_job = start(other_environment, "Explain the application: SECOND_JOB_FACTS_ONLY")
    first_workspace, second_workspace = storage / "first", storage / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()
    workspaces = {str(first.pk): first_workspace, str(second.pk): second_workspace}
    entered = {str(first.pk): threading.Event(), str(second.pk): threading.Event()}
    release = threading.Event()
    calls, calls_lock = {}, threading.Lock()

    def controlled(path, payload, **kwargs):
        with calls_lock:
            calls[payload["request_id"]] = copy.deepcopy(payload)
        entered[payload["request_id"]].set()
        assert release.wait(15), "The test did not release the bounded runtime barrier"
        return response(payload)

    with (
        patch(
            "core.worker.request_workspace", side_effect=lambda request: workspaces[str(request.pk)]
        ),
        patch("core.worker.runtime_call", side_effect=controlled),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first_claim = claim_job()
        assert first_claim.pk == first_job.pk
        one = pool.submit(in_thread, lambda: perform_job(Job.objects.get(pk=first_claim.pk)))
        two = None
        try:
            assert entered[str(first.pk)].wait(10), (
                "The first real worker never reached the runtime"
            )
            second_claim = claim_job()
            assert second_claim is not None and second_claim.pk == second_job.pk
            two = pool.submit(in_thread, lambda: perform_job(Job.objects.get(pk=second_claim.pk)))
            assert entered[str(second.pk)].wait(10), "A free compatible connection was left idle"
            active = list(StepExecution.objects.filter(status="RUNNING"))
            assert len(active) == 2
            assert len({step.job_id for step in active}) == 2
            assert len({step.connection_id for step in active}) == (1 if shared_account else 2)
            assert len({payload["context_id"] for payload in calls.values()}) == 2
            assert {step.public_role for step in active} == {"analyst"}
            assert {item["agent"] for item in calls.values()} == ({"codex"} if shared_account else {"codex", "claude"})
            for current, other in ((first, second), (second, first)):
                payload = calls[str(current.pk)]
                assert payload["workspace"] == str(workspaces[str(current.pk)])
                assert current.need in payload["prompt"] and other.need not in payload["prompt"]
                assert current.environment.context_instructions in payload["prompt"]
                assert other.environment.context_instructions not in payload["prompt"]
        finally:
            release.set()
            one.result(timeout=10)
            if two:
                two.result(timeout=10)
    for job in (first_job, second_job):
        job.refresh_from_db()
        assert job.status == "QUEUED"
        assert job.executions.get().status == "DONE"
        assert (
            job.analysis_run.orchestration["outputs"]["requirement"]
            == RequirementAssessment.model_validate(ready()).model_dump()
        )
    assert not AIConnection.objects.filter(availability="BUSY").exists()


def test_competing_workers_cannot_claim_the_same_job_twice(prepared):
    environment, _, _ = prepared
    assistant()
    _, job = start(environment)
    barrier = threading.Barrier(3)

    def claim():
        barrier.wait(timeout=10)
        value = claim_job()
        return value.pk if value else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(in_thread, claim) for _ in range(2)]
        barrier.wait(timeout=10)
        claimed = [future.result(timeout=10) for future in futures]
    assert claimed.count(job.pk) == 1 and claimed.count(None) == 1
    assert StepExecution.objects.filter(job=job, status="RUNNING").count() == 1
    assert len(job.analysis_run.orchestration["assignments"]) == 1


def test_same_account_aliases_do_not_multiply_parallel_capacity(prepared):
    environment, _, _ = prepared
    original = AIConnection.objects.get(pk=1)
    AIIdentity.objects.filter(pk=original.identity_id).update(account_key="shared-fixture-account")
    alias = assistant("codex", account_key="shared-fixture-account")
    _, first = start(environment)
    _, second = start(environment)
    barrier = threading.Barrier(3)

    def claim():
        barrier.wait(timeout=10)
        value = claim_job()
        return value.pk if value else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(in_thread, claim) for _ in range(2)]
        barrier.wait(timeout=10)
        claimed = [future.result(timeout=10) for future in futures]
    assert claimed.count(first.pk) == 1 and claimed.count(None) == 1
    assert StepExecution.objects.filter(status="RUNNING").count() == 1
    assert set(
        AIConnection.objects.filter(pk__in=[original.pk, alias.pk]).values_list(
            "availability", flat=True
        )
    ) == {"BUSY"}
    second.refresh_from_db()
    assert second.status == "QUEUED" and not second.executions.filter(status="RUNNING").exists()


def test_parallel_account_slots_are_atomic_shared_by_aliases_and_released_individually(prepared, settings):
    from core.providers import capacity_reservations, public, release_connections

    settings.AI_ACCOUNT_CONCURRENCY = 3
    settings.AI_CONCURRENCY = 5
    environment, _, _ = prepared
    original = AIConnection.objects.get(pk=1)
    AIIdentity.objects.filter(pk=original.identity_id).update(account_key="shared-fixture-account")
    alias = assistant("codex", account_key="shared-fixture-account")
    for index in range(6):
        start(environment, f"Inspect application behavior {index}.")
    barrier = threading.Barrier(7)

    def claim():
        barrier.wait(15)
        value = claim_job()
        return value.pk if value else None

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(in_thread, claim) for _ in range(6)]
        barrier.wait(15)
        claimed = [future.result(15) for future in futures]
    ids = [pk for pk in claimed if pk]
    assert len(ids) == len(set(ids)) == 3
    assert len(capacity_reservations()) == 3
    assert public(original)["active_executions"] == public(alias)["active_executions"] == 3
    assert public(alias)["availability"] == "BUSY"
    assert StepExecution.objects.filter(status="RUNNING").count() == 3
    assert len(set(StepExecution.objects.filter(status="RUNNING").values_list("session__context_id", flat=True))) == 3
    # A stopped invocation frees one slot, not every alias/account reservation.
    job = Job.objects.get(pk=ids[0])
    release_connections(job.payload["connection_ids"], job=job)
    assert public(original)["active_executions"] == 2
    assert public(original)["availability"] == "AVAILABLE"
    assert len(capacity_reservations()) == 2
    assert claim_job() is not None
    assert claim_job() is None


def test_global_slots_span_accounts_and_retain_unacknowledged_cancellation(prepared, settings):
    from core.providers import capacity_reservations, public

    settings.AI_ACCOUNT_CONCURRENCY = 4
    settings.AI_CONCURRENCY = 2
    environment, _, _ = prepared
    original = AIConnection.objects.get(pk=1)
    other = assistant()
    first, _ = start(environment)
    start(environment, "Explain a different component.")
    start(environment, "Explain a third component.")
    one, two = claim_job(), claim_job()
    assert one and two and len(capacity_reservations()) == 2
    assert claim_job() is None  # Even another unused account cannot bypass the instance cap.
    assert public(other)["availability"] == "AVAILABLE"
    attempts = cancel_request(first.pk)
    assert attempts
    with patch("core.agent.runtime_call", return_value={"stopped": False}):
        assert not acknowledge_cancellation(one)
    assert len(capacity_reservations()) == 2 and claim_job() is None
    with patch("core.agent.runtime_call", return_value={"stopped": True}):
        assert acknowledge_cancellation(one)
    assert len(capacity_reservations()) == 1
    assert public(original)["active_executions"] == 1
    assert claim_job() is not None


def test_upstream_busy_and_quota_remain_authoritative_with_spare_local_slots(prepared, settings):
    from core.providers import candidates, mark_failure, observe, release_connections

    settings.AI_ACCOUNT_CONCURRENCY = 4
    environment, _, _ = prepared
    start(environment)
    start(environment, "Explain a different component.")
    one, two = claim_job(), claim_job()
    original = AIConnection.objects.get(pk=1)
    mark_failure(original.pk, "BUSY", 60)
    observe(original, {"status": "CONNECTED"})
    assert not candidates()  # Successful auth is not a provider concurrency permit.
    release_connections(one.payload["connection_ids"], job=one)
    assert not candidates()
    mark_failure(original.pk, "QUOTA_EXHAUSTED")
    release_connections(two.payload["connection_ids"], job=two)
    assert not candidates()
    original.refresh_from_db()
    assert original.availability == "QUOTA_EXHAUSTED"


def test_account_editing_and_cli_updates_wait_for_every_active_slot(prepared, settings, client):
    from core.providers import observe, public

    settings.AI_ACCOUNT_CONCURRENCY = 4
    environment, _, _ = prepared
    one_request, _ = start(environment)
    two_request, _ = start(environment, "Explain another part of the application.")
    one, two = claim_job(), claim_job()
    connection = AIConnection.objects.get(pk=1)
    observe(connection, {"status": "CONNECTED"})
    assert public(connection)["availability"] == "AVAILABLE"  # Spare execution slots.
    # Admin changes are still forbidden even if asynchronous health cleared BUSY.
    AIIdentity.objects.filter(pk=connection.identity_id).update(availability="AVAILABLE")
    AIConnection.objects.filter(pk=connection.pk).update(availability="AVAILABLE")
    response = client.put(f"/api/ai-connections/{connection.pk}", {"name": "Changed", "agent": "codex"}, content_type="application/json")
    assert response.status_code == 409
    cancel_request(one_request.pk)
    cancel_request(two_request.pk)
    maintenance = Job.objects.create(kind="cli_update", target="codex")
    assert not Job.objects.filter(status="RUNNING").exists()
    assert claim_job() is None  # Runtime stop is still unacknowledged for both slots.
    with patch("core.agent.runtime_call", return_value={"stopped": True}):
        assert acknowledge_cancellation(one)
        assert claim_job() is None
        assert acknowledge_cancellation(two)
    assert claim_job().pk == maintenance.pk


def test_role_limits_and_oldest_compatible_order_bypass_a_blocked_head(prepared):
    environment, _, _ = prepared
    _, blocked = start(environment, "The older verifier job")
    blocked.payload.update(current_role="verifier", next_checkpoint="verifier")
    blocked.save(update_fields=["payload"])
    _, younger = start(environment, "The younger analyst job")
    # Enqueue under a valid configuration, then simulate an administrator
    # removing capacity while existing work remains queued.
    AIConnection.objects.filter(pk=1).update(roles=["counter_analyst"])
    assert claim_job() is None  # Counter-analyst-only capacity cannot execute either role.
    analyst = assistant("claude", roles=["analyst"])
    selected = claim_job()
    assert selected is not None and selected.pk == younger.pk
    assert selected.executions.get().connection_id == analyst.pk
    assert selected.executions.get().public_role == "analyst"
    blocked.refresh_from_db()
    assert blocked.status == "QUEUED" and blocked.payload["waiting_reason"]
    verifier = assistant("claude", roles=["verifier"])
    _, newest = start(environment, "A still newer analyst job")
    next_claim = claim_job()
    assert next_claim is not None and next_claim.pk == blocked.pk
    assert next_claim.executions.get().connection_id == verifier.pk
    newest.refresh_from_db()
    assert newest.status == "QUEUED"


def test_cancellation_fences_late_output_and_waits_for_exact_runtime_ack(prepared):
    environment, storage, _ = prepared
    request, job = start(environment)
    claimed = claim_job()
    attempt = claimed.executions.get().attempt_id
    entered, release = threading.Event(), threading.Event()

    def controlled(path, payload, **kwargs):
        assert payload["attempt_id"] == str(attempt)
        entered.set()
        assert release.wait(15)
        return response(payload)

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=controlled),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        running = pool.submit(in_thread, lambda: perform_job(Job.objects.get(pk=job.pk)))
        try:
            assert entered.wait(10)
            assert cancel_request(request.pk) == [str(attempt)]
            with patch("core.agent.runtime_call", return_value={"stopped": False}):
                assert not acknowledge_cancellation(job)
            assert AIConnection.objects.get(pk=1).availability == "BUSY"
            _, pending = start(environment, "A different request must wait for released capacity")
            assert claim_job() is None
            with pytest.raises(ExecutionStopped):
                complete_invocation(job, attempt)
        finally:
            release.set()
            running.result(timeout=10)
    job.refresh_from_db()
    assert job.status == "CANCELLED"
    assert not job.analysis_run.orchestration.get("outputs", {}).get("requirement")
    assert job.executions.get().output == {} and job.executions.get().status == "CANCELLED"
    assert not request.versions.exists()
    with patch("core.agent.runtime_call", return_value={"stopped": True}) as stop:
        assert acknowledge_cancellation(job)
    stop.assert_called_once_with(
        "/runs/cancel", {"request_id": str(request.pk), "attempt_id": str(attempt)}, timeout=10
    )
    assert AIConnection.objects.get(pk=1).availability == "AVAILABLE"
    assert claim_job().pk == pending.pk


def test_a_fresh_heartbeat_keeps_a_job_active_beyond_five_minutes(prepared):
    environment, storage, _ = prepared
    _, job = start(environment)
    claimed = claim_job()
    old = timezone.now() - timedelta(minutes=8)
    Job.objects.filter(pk=job.pk).update(started_at=old)
    AnalysisRun.objects.filter(job=job).update(started_at=old)
    StepExecution.objects.filter(job=job).update(started_at=old, heartbeat_at=timezone.now())
    with patch("core.agent.runtime_call") as stop:
        recover_stale_jobs()
        recover_steps()
    stop.assert_not_called()
    job.refresh_from_db()
    assert job.status == "RUNNING" and job.executions.get().status == "RUNNING"
    calls = invoke(claimed, storage)
    job.refresh_from_db()
    assert len(calls) == 1 and job.status == "QUEUED"
    assert job.executions.get().status == "DONE"


def test_a_late_progress_or_run_write_cannot_undo_cancellation(prepared):
    from core.step_execution import save_run
    from core.worker import progress

    environment, _, _ = prepared
    request, job = start(environment)
    claimed = claim_job()
    run = AnalysisRun.objects.get(job=claimed)
    run.execution_attempt = claimed.payload["attempt_id"]
    request.execution_run = run
    cancel_request(request.pk)
    with pytest.raises(ExecutionStopped):
        progress(request, "ANALYZING", "A stale progress event")
    run.status = "RUNNING"
    with pytest.raises(ExecutionStopped):
        save_run(run, ["status"])
    request.refresh_from_db()
    run.refresh_from_db()
    assert request.status == run.status == "CANCELLED"


def test_orphan_recovery_requires_positive_runtime_stop_ack(prepared):
    environment, _, _ = prepared
    _, job = start(environment)
    claim_job()
    StepExecution.objects.filter(job=job).update(
        heartbeat_at=timezone.now() - timedelta(seconds=60)
    )
    with patch("core.agent.runtime_call", return_value={"stopped": False}):
        recover_steps()
    job.refresh_from_db()
    assert job.status == "RUNNING"
    assert job.executions.get().status == "RUNNING"
    assert AIConnection.objects.get(pk=1).availability == "BUSY"


def test_supervisor_does_not_equate_a_negative_stop_ack_with_released_capacity(prepared):
    from core.step_supervisor import stop_runtime

    environment, _, _ = prepared
    _, job = start(environment)
    claimed = claim_job()
    attempt = claimed.executions.get().attempt_id
    with patch("core.agent.runtime_call", return_value={"stopped": False}):
        assert stop_runtime(job, attempt) is False
    assert AIConnection.objects.get(pk=1).availability == "BUSY"
    with patch("core.agent.runtime_call", return_value={"stopped": True}):
        assert stop_runtime(job, attempt) is True


def test_safe_restart_reuses_completed_checkpoints_and_rejects_stale_publication(prepared, bundle):
    environment, storage, source = prepared
    request, job = start(environment)
    initial = claim_job()
    assert [call["profile"] for call in invoke(initial, storage)] == ["requirement"]
    original_requirement = copy.deepcopy(job.analysis_run.orchestration["outputs"]["requirement"])
    interrupted = claim_job()
    interrupted_step = interrupted.executions.get(status="RUNNING")
    old_attempt, old_context = interrupted_step.attempt_id, interrupted_step.session.context_id
    StepExecution.objects.filter(pk=interrupted_step.pk).update(
        heartbeat_at=timezone.now() - timedelta(seconds=60)
    )
    with patch("core.agent.runtime_call", return_value={"stopped": True}):
        recover_steps()
    resumed = claim_job()
    current = resumed.executions.get(status="RUNNING")
    assert current.pk == interrupted_step.pk and current.attempts == 2
    assert current.attempt_id != old_attempt and current.session.context_id != old_context
    stale_run = AnalysisRun.objects.get(job=job)
    stale_run.execution_attempt = old_attempt
    with pytest.raises(ExecutionStopped):
        publish(request.pk, stale_run, bundle)
    assert not request.versions.exists()
    with pytest.raises(ExecutionStopped):
        complete_invocation(job, old_attempt)
    assert [call["profile"] for call in invoke(resumed, storage, omissions.report(source))] == [
        "code"
    ]
    assert (
        AnalysisRun.objects.get(job=job).orchestration["outputs"]["requirement"]
        == original_requirement
    )
    assert job.executions.get(checkpoint="requirement").attempts == 1
    job.refresh_from_db()
    assert job.payload["next_checkpoint"] == "counter_independent"
    assert not request.versions.exists()
    remaining = [
        ("counter_independent", omissions.report(source, exception=True)),
        (
            "comparison",
            {
                "status": "APPROVED",
                "summary": "The independent exception requires scope qualification.",
                "issues": [],
                "verification": None,
            },
        ),
        ("verifier", omissions.verification(source)),
        ("writer", bundle.model_dump()),
    ]
    final_attempt = None
    for checkpoint, output in remaining:
        claimed = claim_job()
        assert claimed.pk == job.pk and claimed.payload["next_checkpoint"] == checkpoint
        final_attempt = claimed.payload["attempt_id"]
        assert len(invoke(claimed, storage, output)) == 1
    request.refresh_from_db()
    job.refresh_from_db()
    assert request.status == "READY" and job.status == "DONE", request.error
    assert request.versions.count() == 1
    assert request.versions.get().artifacts.count() == 2
    assert job.executions.get(checkpoint="requirement").attempts == 1
    perform_job(job, attempt_id=final_attempt)
    assert request.versions.count() == 1
    assert request.versions.get().artifacts.count() == 2


def test_user_clarification_releases_capacity_and_resumes_the_same_job_after_validated_steps(
    prepared,
):
    environment, storage, source = prepared
    request, job = start(environment)
    invoke(claim_job(), storage)
    needs_answer = omissions.report(source)
    needs_answer["questions"] = [
        {"id": "scope", "question": "Should migrated contracts stay eligible for cancellation?"}
    ]
    invoke(claim_job(), storage, needs_answer)
    request.refresh_from_db()
    job.refresh_from_db()
    assert request.status == "NEEDS_CLARIFICATION" and job.status == "DONE"
    assert AIConnection.objects.get(pk=1).availability == "AVAILABLE"
    assert not request.versions.exists()
    requirement = copy.deepcopy(
        AnalysisRun.objects.get(job=job).orchestration["outputs"]["requirement"]
    )
    _, other = start(environment, "A different job can use the released slot")
    claimed_other = claim_job()
    assert claimed_other.pk == other.pk
    invoke(claimed_other, storage)
    enqueue_analysis(
        request.pk,
        answers={"scope": "Preserve the existing migration exception."},
        expected_decision_revision=0,
    )
    assert request.analysis_runs.count() == 1
    assert Job.objects.filter(kind="analysis", target=str(request.pk)).count() == 1
    resumed = claim_job()
    assert resumed.pk == job.pk
    assert [call["profile"] for call in invoke(resumed, storage, omissions.report(source))] == [
        "code"
    ]
    assert AnalysisRun.objects.get(job=job).orchestration["outputs"]["requirement"] == requirement
    assert job.executions.get(checkpoint="requirement").attempts == 1
    assert job.executions.get(checkpoint="analyst").attempts == 2
