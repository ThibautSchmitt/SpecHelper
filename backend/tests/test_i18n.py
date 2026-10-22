import json
from unittest.mock import patch

import pytest

from core.i18n import FRENCH, translate
from core.models import InstanceSettings, Request
from core.results import publish
from core.services import continue_conversation, enqueue_analysis
from core.worker import claim_job, perform_job

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("language", ["en", "fr"])
def test_instance_language_is_validated_and_frozen_per_request(
    client, environment, bundle, language
):
    settings = {"name": "SpecHelper", "primary_color": "#2563eb", "language": language}
    saved = client.put("/api/settings", data=json.dumps(settings), content_type="application/json")
    assert saved.status_code == 200 and saved.json()["language"] == language
    invalid = client.put(
        "/api/settings",
        data=json.dumps({**settings, "language": "de"}),
        content_type="application/json",
    )
    assert invalid.status_code == 422
    assert client.get("/api/settings").json()["language"] == language
    created = client.post(
        "/api/requests",
        data=json.dumps({"environment_id": environment.pk, "need": "Export active contracts"}),
        content_type="application/json",
    )
    assert created.status_code == 201
    request = Request.objects.get(pk=created.json()["id"])
    assert request.language == language
    other = "fr" if language == "en" else "en"
    InstanceSettings.objects.filter(pk=1).update(language=other)
    request.refresh_from_db()
    assert request.language == language
    request.baseline = [{"repository": "fixture/contracts", "branch": "main", "sha": "a" * 40}]
    request.save()
    first = publish(request.pk, None, bundle)
    artifacts = {a.name: a.content for a in first.artifacts.all()}
    assert "## " + translate("Context", language) in artifacts["ticket.md"]
    assert "## " + translate("Repositories and baseline SHAs", language) in artifacts["goal.md"]
    assert "a" * 40 in artifacts["goal.md"]
    assert first.language == language
    continue_conversation(request.pk, "Preserve existing behavior", 1)
    second = publish(request.pk, None, bundle)
    assert second.language == language
    assert {a.name: a.content for a in first.artifacts.all()} == artifacts
    assert client.get(f"/api/requests/{request.pk}/versions/1").json()["language"] == language


@pytest.mark.parametrize("language", ["en", "fr"])
def test_every_comparison_role_receives_the_frozen_output_language(
    environment, storage, bundle, code_report, language
):
    request = Request.objects.create(
        environment=environment,
        need="Export active contracts",
        language=language,
        confrontation=True,
    )
    enqueue_analysis(request.pk)
    seen = []

    def caller(path, payload, **kwargs):
        import uuid

        seen.append(payload)
        assert (
            "OUTPUT LANGUAGE: " + ("French" if language == "fr" else "English") in payload["prompt"]
        )
        assert '"output_language": "' + language + '"' in payload["prompt"]
        if payload["profile"] == "requirement":
            output = {
                "status": "READY_TO_ANALYZE",
                "understanding": "Export active contracts",
                "questions": [],
                "ticket": None,
                "complexity": "simple",
            }
        elif payload["profile"] in {"code", "independent"}:
            output = code_report
        elif payload["profile"] == "reviewer_writer":
            output = {
                "status": "APPROVED",
                "summary": "Sourced conclusions compared",
                "issues": [],
                "verification": None,
            }
        else:
            assert payload["profile"] == "synthesis"
            output = {
                "agreements": ["Minimal change"],
                "divergences": [],
                "result": bundle.model_dump(),
            }
        return {"session_id": payload["session_id"] or str(uuid.uuid4()), "output": output}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=caller),
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY", request.error
    assert [p["profile"] for p in seen] == [
        "requirement",
        "code",
        "independent",
        "reviewer_writer",
        "synthesis",
    ]
    assert len({p["context_id"] for p in seen}) == 3
    assert request.versions.get().language == language


def test_historical_translation_resources_are_explicit_and_readable():
    from core.i18n import LEGACY, legacy

    for key, value in LEGACY.items():
        assert legacy(key) == value
    assert translate("Context", "en") == "Context"
    assert translate("Context", "fr") == FRENCH["Context"]


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("comparison", [False, True])
def test_generated_file_bodies_follow_language_in_normal_and_comparison_flows(
    client, environment, storage, bundle, code_report, language, comparison
):
    import uuid

    from core.artifacts import ArtifactOutput

    marker = translate("Expected behavior", language)

    def localized(value):
        if isinstance(value, dict):
            return {key: localized(item) for key, item in value.items()}
        if isinstance(value, list):
            return [localized(item) for item in value]
        return marker

    output = bundle.model_dump()
    output["ticket"] = localized(output["ticket"])
    output["goal"] = localized(output["goal"])
    output["goal"]["relevant_files"] = ["contracts/export.py: active_contracts"]
    output["technical_summary"] = marker
    output = ArtifactOutput.model_validate(output)
    request = Request.objects.create(
        environment=environment,
        need="Export active contracts",
        language=language,
        confrontation=comparison,
    )
    enqueue_analysis(request.pk)

    def caller(path, payload, **kwargs):
        prompt = payload["prompt"]
        assert "OUTPUT LANGUAGE: " + ("French" if language == "fr" else "English") in prompt
        assert "every natural-language value" in prompt
        assert "every section of goal.md" in prompt
        if payload["profile"] == "requirement":
            response = {
                "status": "READY_TO_ANALYZE",
                "understanding": marker,
                "questions": [],
                "ticket": None,
                "complexity": "simple",
            }
        elif payload["profile"] in {"code", "independent"}:
            response = code_report
        elif payload["profile"] == "reviewer_writer":
            response = {"status": "APPROVED", "summary": marker, "issues": [], "verification": None}
        else:
            assert (
                "Write all narrative content of ticket.md and goal.md in output_language" in prompt
            )
            response = (
                {"agreements": [marker], "divergences": [], "result": output.model_dump()}
                if comparison
                else {"analysis": code_report, "result": output.model_dump()}
            )
        return {"session_id": payload["session_id"] or str(uuid.uuid4()), "output": response}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=caller),
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    assert request.status == "READY", request.error
    version = request.versions.get()
    assert version.ticket == output.ticket.model_dump()
    assert version.technical_summary == marker
    for name in ("ticket.md", "goal.md"):
        downloaded = client.get(f"/api/requests/{request.pk}/versions/1/artifacts/{name}")
        assert downloaded.status_code == 200
        content = downloaded.content.decode()
        assert marker in content
        assert "## " + translate("Acceptance criteria", language) in content
        assert content == version.artifacts.get(name=name).content
    goal = version.artifacts.get(name="goal.md").content
    assert "contracts/export.py: active_contracts" in goal
    assert "## " + translate("Implementation guidance", language) in goal
