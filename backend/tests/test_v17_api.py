"""Question exports and transfers preserve version provenance and workflow isolation."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from core.models import (
    AnalysisRun,
    Environment,
    GeneratedArtifact,
    GitHubConnection,
    InstanceSettings,
    Job,
    QuestionDocument,
    Request,
    ResultVersion,
)
from core.question_outputs import render_answer
from core.secrets import encrypt

pytestmark = pytest.mark.django_db


@pytest.fixture
def question(environment):
    return Request.objects.create(
        workflow="question",
        environment=environment,
        language="en",
        environment_name_snapshot=environment.name,
        need="How are active contracts selected?",
    )


@pytest.fixture
def answer(question):
    explanation = {
        "title": "Active contract selection",
        "summary": "The service excludes closed contracts.",
        "business_explanation": "Only active contracts are exported.",
        "technical_explanation": "ExportService selects status=active.",
        "verified_facts": ["The query filters by active status."],
        "inferences": ["The filter also affects scheduled exports."],
        "uncertainties": ["Scheduled execution was not exercised."],
        "rules": ["Closed contracts are excluded."],
        "references": [
            {
                "repository": "company/backend",
                "path": "contracts/export.py",
                "symbol": "ExportService",
            }
        ],
    }
    baseline = [{"repository": "company/backend", "branch": "main", "sha": "a" * 40}]
    value = ResultVersion.objects.create(
        request=question,
        number=1,
        status="READY",
        language="en",
        explanation=explanation,
        baseline=baseline,
        environment_name="Staging",
    )
    GeneratedArtifact.objects.create(
        version=value, name="answer.md", content=render_answer(explanation, baseline, "en")
    )
    question.status = "READY"
    question.save()
    return value


def post(client, url, payload):
    return client.post(url, payload, content_type="application/json")


def test_create_upload_and_shared_queue(environment, storage):
    client = Client()
    ordinary = Request.objects.create(environment=environment, need="Add a new export filter.")
    response = post(
        client,
        "/api/questions",
        {
            "environment_id": environment.id,
            "need": "How are active contracts selected?",
            "confrontation": True,
        },
    )
    assert response.status_code == 201, response.content
    value = response.json()
    assert value["workflow"] == "question"
    prefix = f"/api/questions/{value['id']}"
    upload = client.post(
        prefix + "/attachments",
        {"file": SimpleUploadedFile("scenario.md", b"Describe active status.")},
    )
    assert upload.status_code == 201
    attachment = upload.json()
    download = client.get(prefix + "/attachments/" + attachment["id"])
    assert b"".join(download.streaming_content) == b"Describe active status."
    started = post(client, prefix + "/analyze", {})
    assert started.status_code == 200, started.content
    assert started.json()["status"] == "QUEUED"
    question = Request.objects.get(pk=value["id"])
    assert question.baseline[0]["sha"] == "a" * 40
    assert AnalysisRun.objects.get(request=question).job.kind == "analysis"
    assert Job.objects.filter(target=str(question.id)).count() == 1
    assert not GeneratedArtifact.objects.filter(version__request=question).exists()
    assert post(client, prefix + "/analyze", {}).status_code == 409
    assert client.delete(prefix + "/attachments/" + attachment["id"]).status_code == 409
    assert client.get(f"/api/requests/{question.id}").status_code == 404
    assert client.get(f"/api/questions/{ordinary.id}").status_code == 404
    assert [item["id"] for item in client.get("/api/questions").json()] == [str(question.id)]
    assert str(question.id) not in [item["id"] for item in client.get("/api/requests").json()]


def test_question_comparison_and_blank_guards(environment, storage):
    client = Client()
    InstanceSettings.objects.update_or_create(pk=1, defaults={"allow_confrontation": False})
    created = post(
        client,
        "/api/questions",
        {
            "environment_id": environment.id,
            "need": "How is status computed?",
            "confrontation": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["confrontation"] is True
    assert created.json()["analysis_protocol"] == "2.4"
    assert (
        post(
            client,
            "/api/questions",
            {
                "environment_id": environment.id,
                "need": " " * 20,
            },
        ).status_code
        == 422
    )
    assert Request.objects.count() == 1


def test_version_copy_and_document_formats_preserve_selected_source(answer, storage):
    client = Client()
    prefix = f"/api/questions/{answer.request_id}/versions/1"
    value = client.get(prefix).json()
    download = client.get(prefix + "/artifacts/answer.md")
    assert download.content.decode() == value["answer_markdown"]
    assert value["explanation"] == answer.explanation
    assert "goal.md" not in value["artifacts"] and "ticket.md" not in value["artifacts"]
    for kind in ("business", "technical", "mixed"):
        created = post(client, prefix + "/documents", {"kind": kind})
        assert created.status_code == 201, created.content
        document = created.json()
        assert document["source_version"] == 1
        assert document["baseline"] == answer.baseline
        assert document["language"] == "en"
        assert "a" * 40 in document["markdown"]
        assert client.get(document["download_url"]).content.decode() == document["markdown"]
        if kind == "business":
            assert "Only active contracts" in document["markdown"]
            assert "ExportService selects" not in document["markdown"]
        if kind == "technical":
            assert "ExportService selects" in document["markdown"]
            assert "Only active contracts" not in document["markdown"]
    assert len(client.get(prefix + "/documents").json()) == 3
    document = QuestionDocument.objects.first()
    document.markdown = "Overwrite"
    with pytest.raises(ValueError, match="immutable"):
        document.save()
    assert Job.objects.count() == 0
    assert post(client, prefix + "/documents", {"kind": "pdf"}).status_code == 422
    assert client.get(prefix + "/artifacts/goal.md").status_code == 422


def test_transfer_requires_explicit_change_and_creates_independent_requests(answer, storage):
    client = Client()
    prefix = f"/api/questions/{answer.request_id}"
    preview = client.get(prefix + "/versions/1/transfer").json()
    assert preview["environment_id"] == answer.request.environment_id
    assert answer.request.need in preview["content"]
    assert str(answer.request_id) in preview["content"]
    assert "a" * 40 in preview["content"]
    assert (
        post(
            client,
            prefix + "/requests",
            {
                "source_version": 1,
                "environment_id": answer.request.environment_id,
                "need": " " * 20,
            },
        ).status_code
        == 422
    )
    other = Environment.objects.create(name="Other", status="READY")
    derived = []
    for environment_id in (answer.request.environment_id, other.id):
        created = post(
            client,
            prefix + "/requests",
            {
                "source_version": 1,
                "environment_id": environment_id,
                "need": "Add an option to export closed contracts.",
            },
        )
        assert created.status_code == 201, created.content
        value = Request.objects.get(pk=created.json()["id"])
        derived.append(value)
        assert value.workflow == "request" and value.status == "DRAFT"
        assert value.environment_id == environment_id
        assert value.source_question_version_id == answer.id
        assert not value.ai_sessions.exists() and not value.versions.exists()
        attachment = value.attachments.get()
        assert attachment.source_question_version_id == answer.id
        assert Path(attachment.path).read_text() == preview["content"]
        assert str(value.id) in attachment.path
        assert value.context_snapshot == {} and value.baseline == []
    assert derived[0].attachments.get().path != derived[1].attachments.get().path
    assert len(client.get(prefix).json()["derived_requests"]) == 2
    assert not Job.objects.exists()
    first = derived[0]
    attachment = first.attachments.get()
    assert client.delete(f"/api/requests/{first.id}/attachments/{attachment.id}").status_code == 200
    assert not first.attachments.exists()
    assert first.source_question_version_id == answer.id


def test_transfer_is_frozen_excludes_dialogue_and_rechecks_new_baseline(answer, storage):
    client = Client()
    prefix = f"/api/questions/{answer.request_id}"
    answer.request.messages.create(
        role="assistant", kind="internal", content="PRIVATE INTERNAL NOTES"
    )
    created = post(
        client,
        prefix + "/requests",
        {
            "source_version": 1,
            "environment_id": answer.request.environment_id,
            "need": "Add a filter to export closed contracts.",
        },
    )
    derived = Request.objects.get(pk=created.json()["id"])
    path = Path(derived.attachments.get().path)
    original = path.read_text()
    assert "PRIVATE INTERNAL NOTES" not in original
    source = answer.request
    ResultVersion.objects.create(
        request=source,
        number=2,
        status="READY",
        language="en",
        explanation={**answer.explanation, "summary": "New conclusions"},
        baseline=[{**answer.baseline[0], "sha": "b" * 40}],
        environment_name="Staging",
    )
    repository = source.environment.repositories.get()
    repository.sha = "c" * 40
    repository.save()
    assert path.read_text() == original
    started = post(client, f"/api/requests/{derived.id}/analyze", {})
    assert started.status_code == 200, started.content
    derived.refresh_from_db()
    assert derived.baseline[0]["sha"] == "c" * 40
    assert "a" * 40 in path.read_text()
    assert "c" * 40 not in path.read_text()
    assert not source.ai_sessions.filter(pk__in=derived.ai_sessions.values("pk")).exists()


def test_exports_redact_current_credentials_and_allow_removing_transfer(answer, storage):
    secret = "fixture-question-private-token"
    GitHubConnection.objects.create(pk=1, secret=encrypt(secret))
    ResultVersion.objects.filter(pk=answer.pk).update(
        explanation={**answer.explanation, "summary": f"Avoid exposing {secret}."}
    )
    client = Client()
    prefix = f"/api/questions/{answer.request_id}"
    preview = client.get(prefix + "/versions/1/transfer")
    assert secret not in preview.content.decode()
    assert "[REDACTED]" in preview.json()["content"]
    document = post(client, prefix + "/versions/1/documents", {"kind": "mixed"})
    assert secret not in document.content.decode()
    created = post(
        client,
        prefix + "/requests",
        {
            "source_version": 1,
            "environment_id": answer.request.environment_id,
            "need": "Add a new selection rule for closed contracts.",
            "include_context": False,
        },
    )
    value = Request.objects.get(pk=created.json()["id"])
    assert not value.attachments.exists()
    assert value.source_question_version_id == answer.pk


def test_incomplete_and_cross_question_sources_are_rejected(answer, environment, storage):
    client = Client()
    other = Request.objects.create(
        workflow="question", environment=environment, need="Other question"
    )
    prefix = f"/api/questions/{other.id}/versions/1"
    assert client.get(prefix + "/transfer").status_code == 404
    assert post(client, prefix + "/documents", {"kind": "mixed"}).status_code == 404
    incomplete = ResultVersion.objects.create(
        request=other,
        number=1,
        status="ERROR",
        language="en",
        explanation={},
        environment_name="Other",
    )
    assert client.get(prefix + "/transfer").status_code == 409
    created = post(
        client, f"/api/questions/{answer.request_id}/versions/1/documents", {"kind": "mixed"}
    )
    document_id = created.json()["id"]
    assert client.get(prefix + f"/documents/{document_id}/download").status_code == 409
    assert incomplete.explanation == {}


def test_clarification_and_continuation_use_existing_conversation(question, storage, answer):
    client = Client()
    question.status = "NEEDS_CLARIFICATION"
    question.questions = [{"id": "scope", "question": "Which contract status?"}]
    question.baseline = answer.baseline
    question.save()
    prefix = f"/api/questions/{question.id}"
    invalid = post(client, prefix + "/answers", {"answers": {}})
    assert invalid.status_code == 422
    resumed = post(client, prefix + "/answers", {"answers": {"scope": "Active only"}})
    assert resumed.status_code == 200, resumed.content
    assert question.messages.filter(kind="answer").count() == 1
    question.status = "READY"
    question.save()
    assert (
        post(
            client,
            prefix + "/continue",
            {
                "message": "What about scheduled exports?",
                "expected_version": 2,
            },
        ).status_code
        == 409
    )
    continued = post(
        client,
        prefix + "/continue",
        {
            "message": "What about scheduled exports?",
            "expected_version": 1,
        },
    )
    assert continued.status_code == 200, continued.content
    assert continued.json()["status"] == "CONTINUING_CONVERSATION"
    assert question.messages.filter(kind="followup").count() == 1
    assert question.analysis_runs.count() == 2


def test_question_actions_preserve_document_and_transfer_sources(answer, storage):
    from core import question_actions as actions

    document = actions.create_document(answer.request_id, 1, "technical")
    assert str(answer.request_id) in document.markdown
    assert "v1" in document.markdown
    preview = actions.transfer_preview(answer.request_id, 1)
    derived = actions.create_request(
        answer.request_id, 1, answer.request.environment_id, "Add a new selection option."
    )
    attachment = derived.attachments.get()
    assert Path(attachment.path).read_text() == preview["content"]
    assert attachment.source_question_version == answer
    assert derived.source_question_version == answer
    assert not derived.ai_sessions.exists()
    assert not derived.versions.exists()
    assert not Job.objects.exists()


@pytest.mark.parametrize("kind", ["transfer", "document"])
def test_invalid_exports_do_not_echo_private_validation_input(answer, storage, kind):
    private = "/private/tmp/question-private-session"
    ResultVersion.objects.filter(pk=answer.pk).update(
        explanation={**answer.explanation, "summary": private}
    )
    client = Client()
    prefix = f"/api/questions/{answer.request_id}/versions/1"
    response = (
        client.get(prefix + "/transfer")
        if kind == "transfer"
        else post(client, prefix + "/documents", {"kind": "mixed"})
    )
    assert response.status_code == 422
    assert private not in response.content.decode()
    assert "cannot be exported safely" in response.json()["detail"]
    assert not QuestionDocument.objects.exists()


def test_transfer_rejects_empty_need_and_preserves_short_need_for_scope_clarification(answer, storage):
    response = post(
        Client(),
        f"/api/questions/{answer.request_id}/requests",
        {"source_version": 1, "environment_id": answer.request.environment_id, "need": " "},
    )
    assert response.status_code == 422
    assert not Request.objects.filter(source_question_version=answer).exists()
    response = post(
        Client(),
        f"/api/questions/{answer.request_id}/requests",
        {"source_version": 1, "environment_id": answer.request.environment_id, "need": "Help"},
    )
    assert response.status_code == 201
    assert response.json()["scope_assessment"]["status"] == "NEEDS_CLARIFICATION"
