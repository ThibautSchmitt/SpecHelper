import uuid
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Job, Request
from core.services import add_attachment, continue_conversation, enqueue_analysis
from core.worker import claim_job, fail_analysis, perform_job

pytestmark = pytest.mark.django_db


def assessment(complexity="simple"):
    return {
        "status": "READY_TO_ANALYZE",
        "understanding": "Export active records",
        "questions": [],
        "ticket": None,
        "complexity": complexity,
    }


def run_with(request, storage, outputs):
    sid = request.session.runtime_id or str(uuid.uuid4())
    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch(
            "core.worker.runtime_call",
            side_effect=[{"session_id": sid, "output": o} for o in outputs],
        ) as runtime,
    ):
        perform_job(claim_job())
    request.refresh_from_db()
    return runtime


def test_simple_continuations_keep_session_and_previous_versions(
    environment, storage, bundle, code_report
):
    request = Request.objects.create(environment=environment, need="Export active records")
    enqueue_analysis(request.id)
    first = run_with(
        request, storage, [assessment(), {"analysis": code_report, "result": bundle.model_dump()}]
    )
    assert request.status == "READY"
    assert [c.args[1]["profile"] for c in first.call_args_list] == ["requirement", "code_writer"]
    original = request.versions.get().artifacts.get(name="goal.md").content
    sid = request.session.runtime_id
    for number in (1, 2):
        continue_conversation(request.id, "Confirmer le filtrage des actifs", number)
        resumed = run_with(
            request,
            storage,
            [assessment(), {"analysis": code_report, "result": bundle.model_dump()}],
        )
        assert all(c.args[1]["session_id"] == sid for c in resumed.call_args_list)
    assert list(request.versions.values_list("number", flat=True).order_by("number")) == [1, 2, 3]
    assert request.versions.get(number=1).artifacts.get(name="goal.md").content == original
    assert all(
        run.pipeline == ["requirement", "code", "writer"] for run in request.analysis_runs.all()
    )
    job = Job.objects.latest("id")
    fail_analysis(job, "Late crash")
    request.refresh_from_db()
    job.refresh_from_db()
    assert request.status == "READY" and job.status == "DONE"


@pytest.mark.parametrize("target", ["code", "attachment"])
def test_reviewer_verification_is_targeted_and_bounded(
    environment, storage, bundle, code_report, target
):
    request = Request.objects.create(
        environment=environment, need="Export according to the attached rules"
    )
    add_attachment(request.id, SimpleUploadedFile("rules.txt", b"Active only"))
    enqueue_analysis(request.id)
    outputs = [
        assessment("standard"),
        {
            "observations": [{"attachment": "rules.txt", "facts": ["Actifs"], "uncertainties": []}],
            "questions": [],
        },
        code_report,
        {
            "review": {
                "status": "NEEDS_VERIFICATION",
                "summary": "Verify the selection",
                "issues": [],
                "verification": {
                    "target": target,
                    "questions": ["Are terminated contracts excluded?"],
                },
            },
            "result": None,
        },
        {
            "answers": [
                {
                    "question": "Are terminated contracts excluded?",
                    "answer": "The filter is required.",
                    "evidence": ["contracts/export.py: selection"],
                }
            ],
            "remaining_uncertainties": [],
        },
        bundle.model_dump(),
    ]
    runtime = run_with(request, storage, outputs)
    assert request.status == "READY"
    assert [c.args[1]["profile"] for c in runtime.call_args_list] == [
        "requirement",
        "attachment",
        "code",
        "reviewer_writer",
        target,
        "writer",
    ]
    assert runtime.call_count == 6
    assert all(c.args[1]["database"] is None for c in runtime.call_args_list)
    assert request.analysis_runs.get().status == "READY"


def test_invalid_output_repair_is_bounded_and_preserves_old_result(
    environment, storage, bundle, code_report
):
    request = Request.objects.create(environment=environment, need="Export active records")
    enqueue_analysis(request.id)
    run_with(
        request, storage, [assessment(), {"analysis": code_report, "result": bundle.model_dump()}]
    )
    original = request.versions.get().artifacts.get(name="ticket.md").content
    continue_conversation(request.id, "Clarify", 1)
    runtime = run_with(request, storage, [assessment(), {"private_reasoning": "forbidden"}, {}])
    assert runtime.call_count == 3
    assert request.status == "ERROR"
    assert request.versions.count() == 1
    assert request.versions.get().artifacts.get(name="ticket.md").content == original
    assert request.analysis_runs.latest("number").status == "ERROR"


def test_attachment_names_are_constrained_and_semantically_repaired(
    environment, storage, bundle, code_report
):
    request = Request.objects.create(
        environment=environment, need="Export according to the instruction"
    )
    add_attachment(request.id, SimpleUploadedFile("rules.txt", b"Active only"))
    enqueue_analysis(request.id)
    good = bundle.model_dump()
    good["goal"]["useful_attachments"] = ["rules.txt"]
    import copy

    bad = copy.deepcopy(good)
    bad["goal"]["useful_attachments"] = ["`rules.txt`: summary"]
    review = {"status": "APPROVED", "summary": "Verified", "issues": [], "verification": None}
    runtime = run_with(
        request,
        storage,
        [
            assessment("standard"),
            {"observations": [], "questions": []},
            code_report,
            {"review": review, "result": bad},
            {"review": review, "result": good},
        ],
    )
    assert request.status == "READY"
    assert runtime.call_count == 5
    assert [call.args[1]["profile"] for call in runtime.call_args_list][-2:] == [
        "reviewer_writer",
        "reviewer_writer",
    ]
    schema = runtime.call_args_list[-1].args[1]["schema"]
    assert schema["$defs"]["DevelopmentGoal"]["properties"]["useful_attachments"]["items"][
        "enum"
    ] == ["rules.txt"]
    assert request.versions.get().artifacts.get(name="goal.md").content.endswith("- rules.txt\n")
