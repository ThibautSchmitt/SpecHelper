"""Actual queue checkpoints preserve conditional external-reference provenance."""

import copy
import hashlib
import uuid
from unittest.mock import patch

import pytest
from test_v24_omissions import committed_source as _committed_source
from test_v24_omissions import report, verification
from test_v25_web import Response, install_transport

from core.models import Request
from core.services import enqueue_analysis
from core.worker import claim_job, perform_job
from runtime.broker import Broker

pytestmark = pytest.mark.django_db
committed_source = _committed_source

PAGE = (
    b"<title>Official cancellation rule version 2026</title>"
    b"<p>Official authority: effective 2026-01-01, version 2026 applies to contracts in France.</p>"
)


def official_claim(receipt, identifier="official"):
    return {
        "id": identifier,
        "statement": "The official reference states the scoped contractual rule in France.",
        "kind": "interpretation",
        "basis": "official_rule",
        "status": "supported",
        "scope": {
            "conditions": ["The external reference applies to this contractual version."],
            "period": "Effective 2026-01-01",
            "population": "Contracts in France",
            "sample_limits": "Only the fetched reference version was checked; deployment behavior remains a separate Git claim.",
        },
        "sources": [
            {
                "kind": "web",
                "reference_id": receipt["reference_id"],
                "excerpt": receipt["text"],
                "authority": "Official authority",
                "effective_date": "2026-01-01",
                "version": "2026",
                "jurisdiction": "France",
                "scope": "Contracts",
                "applicability": "current",
                "applicability_notes": "The observed date, version and jurisdiction match this explicitly scoped request.",
            }
        ],
    }


@pytest.mark.parametrize("external_rule", [False, True])
def test_conditional_references_across_independent_queue_steps(
    environment, storage, committed_source, bundle, monkeypatch, external_rule
):
    network = install_transport(
        monkeypatch, [Response(PAGE, headers={"Content-Type": "text/html"}) for _ in range(2)]
    )
    request = Request.objects.create(
        environment=environment,
        analysis_protocol="2.4",
        language="en",
        need=(
            "Explain the frozen cancellation guard against the applicable official French contractual rule."
            if external_rule
            else "Explain only this application's cancellation guard; no external rule is involved."
        ),
    )
    enqueue_analysis(request.pk)
    receipts, invocations, failures = [], [], []
    outputs = [
        {
            "status": "READY_TO_ANALYZE",
            "understanding": "Explain scoped cancellation conditions.",
            "questions": [],
            "ticket": None,
            "complexity": "simple",
            "intent": "bug",
        },
        {**report(committed_source), "uncertainties": ["PRIVATE_ANALYST_WEB_FINDING"]},
        report(committed_source, exception=True),
        {
            "status": "APPROVED",
            "summary": "Verify independently observed cancellation conditions.",
            "issues": [],
            "verification": None,
        },
        verification(committed_source),
        bundle.model_dump(),
    ]

    def invoke_checked(path, payload, **kwargs):
        assert path == "/run"
        index = len(invocations)
        invocations.append(copy.deepcopy(payload))
        output = outputs.pop(0)
        service_receipts = []
        broker = Broker(payload["agent"], {}, 10, web=payload["web_references"])
        assert (broker.web is not None) is (index not in {0, 5})
        if index == 0:
            assert network == []
        if index == 2:
            assert "PRIVATE_ANALYST_WEB_FINDING" not in payload["prompt"]
            assert payload["context_id"] != invocations[1]["context_id"]
            if external_rule:
                assert receipts[0]["reference_id"] not in payload["prompt"]
                assert official_claim(receipts[0])["statement"] not in payload["prompt"]
        if external_rule and index in {1, 2}:
            assert broker.web is not None
            url = "https://official.example.org/" + (
                "rule" if index == 1 else "independent-reference"
            )
            receipt = broker.web.read(url)
            service_receipts = broker.web.receipts
            receipts.append(copy.deepcopy(receipt))
            output["claims"].append(official_claim(receipt))
        if external_rule and index == 4:
            output["report"]["claims"] += [
                official_claim(receipts[0], "analyst:official"),
                official_claim(receipts[1], "counter:official"),
            ]
        return {"output": output, "web_checks": service_receipts, "session_id": str(uuid.uuid4())}

    def invoke(path, payload, **kwargs):
        try:
            return invoke_checked(path, payload, **kwargs)
        except Exception as error:
            failures.append(repr(error))
            raise

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        for _ in range(12):
            job = claim_job()
            if job is None:
                break
            perform_job(job)
            request.refresh_from_db()
            if request.status in {"READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"}:
                break
    assert request.status == "READY", (request.error, failures)
    assert not outputs and len(invocations) == 6
    assert [row["web_references"] for row in invocations] == [False, True, True, True, True, False]
    version = request.versions.get()
    assert version.run.orchestration["inferred_intent"] == "bug"
    checked = version.evidence
    if external_rule:
        assert len(network) == len(receipts) == len(checked["web_references"]) == 2
        official = [claim for claim in checked["claims"] if claim["basis"] == "official_rule"]
        assert len(official) == 2 and all(claim["status"] == "supported" for claim in official)
        assert all(receipt["sha256"] == hashlib.sha256(PAGE).hexdigest() for receipt in receipts)
        assert all(
            receipt["text_sha256"] == hashlib.sha256(receipt["text"].encode()).hexdigest()
            for receipt in receipts
        )
        stored = request.analysis_runs.get().orchestration["web_checks"]
        assert {row["reference_id"] for row in stored} == {row["reference_id"] for row in receipts}
        for artifact in version.artifacts.all():
            for receipt in receipts:
                assert receipt["url"] in artifact.content
                assert receipt["consulted_at"] in artifact.content
                assert receipt["sha256"] in artifact.content
            assert "2026-01-01" in artifact.content
    else:
        assert network == receipts == checked["web_references"] == []
        assert request.analysis_runs.get().orchestration.get("web_checks", []) == []
