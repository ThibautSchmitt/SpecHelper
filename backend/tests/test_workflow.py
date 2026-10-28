import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.errors import HttpError

from core.agent import AgentOutput, UnderstandingOutput, prompt
from core.models import AIConnection, AISession, AnalysisResult, ConnectionAttempt, Job, Request
from core.services import add_attachment, enqueue_analysis
from core.worker import analyze, claim_job, perform_job, work_once

pytestmark = pytest.mark.django_db


def test_unauthenticated_role_configuration_blocks_new_analysis(client, environment):
    AIConnection.objects.filter(pk=1).update(status="DISCONNECTED", availability="UNKNOWN")
    request = Request.objects.create(environment=environment, need="Export contracts")
    response = client.post(f"/api/requests/{request.id}/analyze")
    assert response.status_code == 409
    request.refresh_from_db()
    assert request.status == "DRAFT"
    assert request.baseline == []
    assert not AISession.objects.filter(request=request).exists()
    assert not Job.objects.exists()


def test_another_provider_login_does_not_block_available_assistant(environment):
    from datetime import timedelta

    from django.utils import timezone

    ConnectionAttempt.objects.create(
        provider="claude", expires_at=timezone.now() + timedelta(minutes=5)
    )
    request = Request.objects.create(environment=environment, need="Export contracts")
    enqueue_analysis(request.id)
    assert Request.objects.get(pk=request.pk).session.agent == "codex"
    assert Job.objects.count() == 1


def test_baseline_frozen_and_double_launch_rejected(environment):
    request = Request.objects.create(environment=environment, need="Export active contracts")
    queued = enqueue_analysis(request.id)
    environment.repositories.update(sha="b" * 40, branch="develop")
    queued.refresh_from_db()
    assert queued.baseline == [{"repository": "company/backend", "branch": "main", "sha": "a" * 40}]
    assert AISession.objects.filter(request=request).count() == 1
    with pytest.raises(HttpError, match="already"):
        enqueue_analysis(request.id)
    assert Job.objects.count() == 1


def test_unready_environment_is_rejected(environment):
    environment.status = "SYNCING"
    environment.save()
    request = Request.objects.create(environment=environment, need="Export contracts")
    with pytest.raises(HttpError, match="synchronized"):
        enqueue_analysis(request.id)
    assert not Job.objects.exists()


def test_upload_isolated_and_frozen(environment, storage):
    request = Request.objects.create(environment=environment, need="Export contracts")
    other = Request.objects.create(environment=environment, need="Another need")
    first = add_attachment(request.id, SimpleUploadedFile("../../capture.txt", b"example"))
    second = add_attachment(other.id, SimpleUploadedFile("capture.txt", b"other"))
    assert first.name == "capture.txt"
    assert Path(first.path).parent == storage / "requests" / str(request.id) / "attachments"
    assert Path(first.path).read_bytes() == b"example"
    assert first.path != second.path
    enqueue_analysis(request.id)
    with pytest.raises(HttpError, match="frozen"):
        add_attachment(request.id, SimpleUploadedFile("more.txt", b"later"))


@pytest.mark.parametrize(
    "name", ["script.sh", "script.py", "active.html", "image.svg", "macro.docm"]
)
def test_executable_attachment_formats_rejected(environment, storage, name):
    request = Request.objects.create(environment=environment, need="Export contracts")
    with pytest.raises(HttpError, match="format"):
        add_attachment(request.id, SimpleUploadedFile(name, b"test"))


def test_clarification_resumes_same_session(environment, storage, bundle, code_report):
    request = Request.objects.create(environment=environment, need="Export contracts")
    enqueue_analysis(request.id)
    session_id = str(uuid.uuid4())
    replies = [
        {
            "session_id": session_id,
            "output": {
                "status": "NEEDS_CLARIFICATION",
                "understanding": "An export is requested",
                "questions": [{"id": "Q1", "question": "Which contracts?"}],
                "ticket": None,
                "complexity": "simple",
            },
        },
        {
            "session_id": session_id,
            "output": {
                "status": "READY_TO_ANALYZE",
                "understanding": "Active contracts",
                "questions": [],
                "ticket": None,
                "complexity": "simple",
            },
        },
        {
            "session_id": session_id,
            "output": {"analysis": code_report, "result": bundle.model_dump()},
        },
    ]
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=replies) as runtime,
    ):
        analyze(request.id)
        request.refresh_from_db()
        assert request.status == "NEEDS_CLARIFICATION"
        with pytest.raises(HttpError, match="every"):
            enqueue_analysis(request.id, {})
        enqueue_analysis(request.id, {"Q1": "Active contracts"})
        analyze(request.id)
    request.refresh_from_db()
    assert request.status == "READY"
    assert request.session.runtime_id == session_id
    assert runtime.call_args_list[0].args[1]["session_id"] is None
    assert all(call.args[1]["session_id"] == session_id for call in runtime.call_args_list[1:])
    assert all(call.args[1]["database"] is None for call in runtime.call_args_list)
    assert [call.args[1]["phase"] for call in runtime.call_args_list] == [
        "understanding",
        "understanding",
        "analysis",
    ]
    result = AnalysisResult.objects.get(request=request)
    assert "a" * 40 in request.versions.get().artifacts.get(name="goal.md").content
    assert "## Acceptance criteria" in result.markdown
    assert request.conversation[0]["answers"] == {"Q1": "Active contracts"}


def test_timeout_keeps_runtime_session_and_marks_error(environment, storage):
    request = Request.objects.create(environment=environment, need="Export contracts")
    enqueue_analysis(request.id)
    job = claim_job()
    session_id = str(uuid.uuid4())
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call", return_value={"session_id": session_id, "timed_out": True}
        ),
    ):
        perform_job(job)
    request.refresh_from_db()
    job.refresh_from_db()
    assert request.status == "ERROR"
    assert "five-minute" in request.error
    assert request.session.runtime_id == session_id
    assert job.status == "ERROR"


def test_agent_contract_rejects_inconsistent_results():
    with pytest.raises(ValueError):
        AgentOutput.model_validate(
            {"status": "READY", "understanding": "x", "questions": [], "ticket": None}
        )
    with pytest.raises(ValueError):
        AgentOutput.model_validate(
            {"status": "NEEDS_CLARIFICATION", "understanding": "x", "questions": [], "ticket": None}
        )


def test_understanding_phase_cannot_skip_analysis_with_a_ticket(ticket):
    with pytest.raises(ValueError):
        UnderstandingOutput.model_validate(
            {"status": "READY", "understanding": "Clear need", "questions": [], "ticket": ticket}
        )
    output = UnderstandingOutput.model_validate(
        {
            "status": "READY_TO_ANALYZE",
            "understanding": "Clear need",
            "questions": [],
            "ticket": None,
        }
    )
    assert output.ticket is None


def test_prompt_has_only_attachment_references_and_no_secrets(environment, storage):
    request = Request.objects.create(environment=environment, need="Export contracts")
    add_attachment(
        request.id, SimpleUploadedFile("details.txt", b"FILE-CONTENTS-MUST-NOT-BE-IN-PROMPT")
    )
    rendered = prompt(request, "understanding")
    assert "details.txt" in rendered
    assert "FILE-CONTENTS" not in rendered
    assert "NEEDS_CLARIFICATION" in rendered


def test_api_theme_upload_export_and_cross_origin(client, environment, storage, ticket):
    response = client.put(
        "/api/settings",
        data=json.dumps({"name": "Product team", "primary_color": "#ff8800"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert client.get("/api/settings").json()["name"] == "Product team"
    bad = client.put(
        "/api/settings",
        data=json.dumps({"name": "x", "primary_color": "red;evil"}),
        content_type="application/json",
    )
    assert bad.status_code == 422
    cross_site = client.post(
        "/api/requests",
        data=json.dumps({"need": "Export contracts", "environment_id": environment.id}),
        content_type="application/json",
        HTTP_ORIGIN="https://evil.example",
        HTTP_SEC_FETCH_SITE="cross-site",
    )
    assert cross_site.status_code == 403
    created = client.post(
        "/api/requests",
        data=json.dumps({"need": "Export contracts", "environment_id": environment.id}),
        content_type="application/json",
    )
    assert created.status_code == 201
    request_id = created.json()["id"]
    uploaded = client.post(
        f"/api/requests/{request_id}/attachments",
        {"file": SimpleUploadedFile("spec.pdf", b"%PDF-1.4")},
    )
    assert uploaded.status_code == 201
    response = client.get(f"/api/requests/{request_id}/attachments/{uploaded.json()['id']}")
    assert response.status_code == 200
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "attachment" in response["Content-Disposition"]
    request = Request.objects.get(pk=request_id)
    AnalysisResult.objects.create(request=request, ticket=ticket, markdown="# Ticket\n")
    exported = client.get(f"/api/requests/{request_id}/markdown")
    assert exported.content == b"# Ticket\n"
    assert exported["Content-Type"].startswith("text/markdown")


def test_legacy_supervision_retains_its_technical_guard_without_blocking_scheduler(environment):
    from core.step_supervisor import PROCESSES, poll_processes

    PROCESSES.clear()
    request = Request.objects.create(environment=environment, need="Export contracts")
    enqueue_analysis(request.id)
    with (
        patch("core.step_supervisor.subprocess.Popen") as popen,
        patch("core.step_supervisor.os.killpg") as kill,
        patch("core.step_supervisor.time.monotonic", return_value=0) as clock,
    ):
        popen.return_value.pid = 12345
        popen.return_value.poll.return_value = None
        popen.return_value.wait.return_value = -9
        popen.return_value.returncode = -9
        assert work_once() is True
        assert Job.objects.get().status == "RUNNING"
        popen.return_value.wait.assert_not_called()
        clock.return_value = 296
        poll_processes()
        kill.assert_called_once()
    request.refresh_from_db()
    assert request.status == "ERROR"
    assert Job.objects.get().status == "ERROR"
    assert not PROCESSES
