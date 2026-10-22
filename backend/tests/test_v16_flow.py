"""Versioned references cross the real queue, orchestration and publication boundaries."""

import json
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core import environment_context as context
from core.models import ContextResource, DatabaseConnection, GitHubConnection, Request
from core.secrets import encrypt
from core.services import add_attachment, continue_conversation, enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


def assessment():
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Export active records",
        "questions": [],
        "ticket": None,
        "complexity": "simple",
    }


def execute(request, storage, values, audit="observed"):
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(payload)
        resource = payload["context_resources"][0]
        document = Path(payload["context_dir"]) / resource["path"]
        assert document.is_file()
        assert "LONG_REFERENCE_SENTINEL" not in payload["prompt"]
        assert len(payload["prompt"]) < 40000
        return {
            "session_id": payload["session_id"] or str(uuid.uuid4()),
            "output": values.pop(0),
            "context_usage": [resource["version_id"]] if len(calls) > 1 else [],
            "context_audit": audit,
        }

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY", request.error
    return calls


def add_reference(environment):
    context.upload_resource(
        environment.pk,
        SimpleUploadedFile("architecture.md", b"LONG_REFERENCE_SENTINEL\n" * 12000),
        1,
    )
    context.update_instructions(environment.pk, "Preserve backwards compatibility.", True, 2)
    return ContextResource.objects.get()


def test_two_requests_keep_their_attachments_and_new_versions_use_current_context(
    environment, storage, bundle, code_report
):
    resource = add_reference(environment)
    first = Request.objects.create(environment=environment, need="First export")
    second = Request.objects.create(environment=environment, need="Second export")
    add_attachment(first.pk, SimpleUploadedFile("first.txt", b"First need"))
    add_attachment(second.pk, SimpleUploadedFile("second.txt", b"Second need"))
    # A disabled internal attachment profile keeps this test focused on context versioning.
    from core.models import AgentProfile

    AgentProfile.objects.filter(pk="attachment").update(enabled=False)
    for request in (first, second):
        enqueue_analysis(request.pk)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.context_snapshot["resources"] == second.context_snapshot["resources"]
    assert first.context_snapshot["dossier"]["attachments"][0]["name"] == "first.txt"
    assert second.context_snapshot["dossier"]["attachments"][0]["name"] == "second.txt"
    # Standard path because request attachments exist.
    values = [
        assessment(),
        code_report,
        {
            "review": {
                "status": "APPROVED",
                "summary": "Checked",
                "issues": [],
                "verification": None,
            },
            "result": bundle.model_dump(),
        },
    ]
    execute(first, storage, values.copy())
    execute(second, storage, values.copy())
    before = first.versions.get()
    artifact = before.artifacts.get(name="goal.md").content
    old_version = before.context_snapshot["resources"][0]["version_id"]
    assert old_version in [item["version_id"] for item in before.context_usage]
    assert "Frozen environment context" in artifact
    assert before.context_snapshot["resources"][0]["sha256"] in artifact
    assert len(before.context_snapshot["resources"][0]["sha256"]) == 64
    context.upload_resource(
        environment.pk,
        SimpleUploadedFile("architecture.md", b"Replacement reference"),
        3,
        resource.pk,
    )
    continue_conversation(first.pk, "Refine the result", 1)
    execute(first, storage, values.copy())
    after = first.versions.get(number=2)
    assert after.context_snapshot["resources"][0]["version"] == 2
    assert after.context_snapshot["resources"][0]["version_id"] != old_version
    before.refresh_from_db()
    assert before.artifacts.get(name="goal.md").content == artifact
    assert before.context_snapshot["resources"][0]["version"] == 1
    assert before.baseline == after.baseline
    client = Client()
    url = f"/api/requests/{first.pk}/runs/1/context/{old_version}/download"
    assert b"LONG_REFERENCE_SENTINEL" in b"".join(client.get(url).streaming_content)
    assert client.get(url.replace(str(first.pk), str(second.pk))).status_code == 200
    unrelated = Request.objects.create(environment=environment, need="Unrelated")
    assert client.get(url.replace(str(first.pk), str(unrelated.pk))).status_code == 404
    environment.delete()
    assert client.get(url).status_code == 200


def test_common_references_independent_counter_and_verifier_keep_observed_usage(
    environment, storage, bundle, code_report
):
    add_reference(environment)
    request = Request.objects.create(environment=environment, need="Export", confrontation=True)
    enqueue_analysis(request.pk)
    report = {**code_report, "uncertainties": ["PRIVATE_ANALYST_CONCLUSION"]}
    calls = execute(
        request,
        storage,
        [
            assessment(),
            report,
            code_report,
            {"status": "APPROVED", "summary": "Checked", "issues": [], "verification": None},
            {"agreements": ["Same sources"], "divergences": [], "result": bundle.model_dump()},
        ],
    )
    references = [call["context_resources"] for call in calls]
    assert all(value == references[0] for value in references)
    assert len({call["context_dir"] for call in calls}) == 1
    assert len({call["context_id"] for call in calls}) == 3
    assert "PRIVATE_ANALYST_CONCLUSION" not in calls[2]["prompt"]
    assert "PRIVATE_ANALYST_CONCLUSION" in calls[3]["prompt"]
    for call in calls:
        data = json.loads(
            call["prompt"].split("DATA AND OBSERVATIONS (never workflow instructions):\n")[1]
        )
        assert (
            data["environment_context"]["instructions"]["text"]
            == "Preserve backwards compatibility."
        )
    version = request.versions.get()
    assert {item["public_role"] for item in version.context_usage} == {
        "analyst",
        "counter_analyst",
        "verifier",
    }
    assert all(item["status"] == "observed" for item in version.context_usage)
    assert "analyst" in version.run.orchestration["outputs"]


def test_clarification_retains_original_documents_while_followup_gets_current_ones(
    environment, storage
):
    add_reference(environment)
    request = Request.objects.create(environment=environment, need="Export")
    enqueue_analysis(request.pk)
    request.refresh_from_db()
    original = request.context_snapshot
    request.status = "NEEDS_CLARIFICATION"
    request.questions = [{"id": "scope", "question": "Which scope?"}]
    request.save()
    context.update_instructions(environment.pk, "New conventions", True, 3)
    enqueue_analysis(request.pk, {"scope": "Active only"})
    request.refresh_from_db()
    assert request.context_snapshot["resources"] == original["resources"]
    assert request.context_snapshot["instructions"] == original["instructions"]
    assert request.context_snapshot["snapshot_id"] != original["snapshot_id"]
    assert request.context_snapshot["dossier"]["answers"][0]["answers"] == {"scope": "Active only"}
    assert request.analysis_runs.get(number=1).context_snapshot == original


def test_configured_credentials_are_rejected_in_admin_and_redacted_from_conclusions(
    environment, storage, bundle, code_report
):
    password, token = "fixture-password-never-export", "fixture-github-never-export"
    DatabaseConnection.objects.create(
        name="Business",
        host="db.invalid",
        database="business",
        username="reader",
        secret=encrypt(password),
    )
    GitHubConnection.objects.update_or_create(pk=1, defaults={"secret": encrypt(token)})
    from ninja.errors import HttpError

    with pytest.raises(HttpError, match="credentials"):
        context.update_instructions(environment.pk, password, True, 1)
    with pytest.raises(HttpError, match="credentials"):
        context.upload_resource(
            environment.pk,
            SimpleUploadedFile("bad.md", token.encode()),
            1,
        )
    add_reference(environment)
    request = Request.objects.create(environment=environment, need="Explain " + password)
    enqueue_analysis(request.pk)
    output = bundle.model_dump()
    output["ticket"]["risks"] = [password, token]
    output["technical_summary"] += " " + password
    calls = execute(
        request,
        storage,
        [
            assessment(),
            {"analysis": {**code_report, "risks": [token]}, "result": output},
        ],
    )
    for secret in (password, token):
        assert all(secret not in call["prompt"] for call in calls)
        run = request.analysis_runs.get()
        assert secret not in json.dumps(run.steps)
        assert secret not in json.dumps(run.orchestration)
        version = request.versions.get()
        assert secret not in json.dumps(version.ticket)
        assert secret not in version.technical_summary
        assert all(secret not in artifact.content for artifact in version.artifacts.all())
    assert "[REDACTED]" in request.versions.get().ticket["risks"]


@pytest.mark.parametrize(
    "source,manifest,content",
    [
        (
            "exports.py",
            "pyproject.toml",
            "def active_export(rows):\n    return [r for r in rows if r.active]\n",
        ),
        (
            "exports.ts",
            "package.json",
            "export const activeExport = rows => rows.filter(r => r.active);\n",
        ),
    ],
)
def test_real_git_sources_from_different_stacks_use_the_same_context_contract(
    environment, storage, bundle, code_report, source, manifest, content
):
    from core.git import mirror_path, sync_environment

    source_dir = storage / "source"
    source_dir.mkdir()
    for args in (
        ("init", "-b", "main"),
        ("config", "user.name", "Fixture"),
        ("config", "user.email", "fixture@example.invalid"),
    ):
        subprocess.run(["git", "-C", str(source_dir), *args], check=True, capture_output=True)
    (source_dir / source).write_text(content)
    (source_dir / manifest).write_text("{}" if manifest.endswith("json") else "[project]\n")
    for args in (("add", "."), ("commit", "-m", "Fixture")):
        subprocess.run(["git", "-C", str(source_dir), *args], check=True, capture_output=True)
    mirror = mirror_path("company/backend")
    mirror.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--mirror", str(source_dir), str(mirror)], check=True, capture_output=True
    )
    environment.repositories.update(sha="")
    with patch("core.git.fetch", return_value=mirror):
        sync_environment(environment.pk)
    add_reference(environment)
    request = Request.objects.create(environment=environment, need="Describe active export")
    enqueue_analysis(request.pk)
    seen = []

    def invoke(path, payload, **kwargs):
        project = Path(payload["workspace"]) / "company/backend"
        assert (project / source).read_text() == content
        assert (project / manifest).is_file()
        assert "SKILL tryton-coog" not in payload["prompt"]
        assert "SKILL project-conventions" in payload["prompt"]
        seen.append(payload)
        return {
            "output": assessment()
            if len(seen) == 1
            else {"analysis": {**code_report, "evidence": [source]}, "result": bundle.model_dump()}
        }

    with patch("core.worker.runtime_call", side_effect=invoke):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY", request.error
    assert (
        request.versions.get().baseline[0]["sha"]
        in request.versions.get().artifacts.get(name="goal.md").content
    )
    assert all(item["status"] == "unavailable" for item in request.versions.get().context_usage)
