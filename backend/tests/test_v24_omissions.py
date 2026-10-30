"""Independent coverage finds a decisive exception despite true initial claims."""

import copy
import os
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
import pytest
from psycopg import sql
from pydantic import ValidationError

from core.git import run as git
from core.models import Request
from core.reliable_flow import (
    CoverageAssessment,
    CoverageCodeReport,
    CoverageFinding,
    CoverageQuestionReport,
    OmissionsOrchestrator,
    ReliableOrchestrator,
)
from core.services import enqueue_analysis
from core.worker import claim_job, perform_job

SOURCE = (
    "def can_cancel(order, config):\n"
    '    if config["blocking"] and order.kind != "migration":\n'
    "        return not order.active_benefit\n"
    "    return True\n"
)
EXCEPTION = "Migration imports bypass the ordinary cancellation guard."


@pytest.mark.django_db
@pytest.mark.skipif(
    not os.environ.get("SPECHELPER_TEST_POSTGRES_DSN"),
    reason="Disposable PostgreSQL not configured",
)
def test_database_enabled_pipeline_keeps_lazy_skills_within_current_tool_capabilities(
    environment, storage, committed_source, bundle
):
    from core.models import DatabaseConnection
    from core.postgres import query
    from core.secrets import encrypt
    from runtime.broker import Broker
    from runtime.global_skills import SkillResources

    dsn = os.environ["SPECHELPER_TEST_POSTGRES_DSN"]
    schema = "v24_scope_" + uuid.uuid4().hex[:12]
    role = "v24_reader_" + uuid.uuid4().hex[:12]
    password = "fixture-v24-reader-only"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
        try:
            admin.execute(
                sql.SQL(
                    "CREATE TABLE {}.records (migration bool, cancelled bool, ongoing bool)"
                ).format(sql.Identifier(schema))
            )
            admin.execute(
                sql.SQL("INSERT INTO {}.records VALUES (false,false,true),(true,true,true)").format(
                    sql.Identifier(schema)
                )
            )
            admin.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            admin.execute(
                sql.SQL("GRANT SELECT ON {}.records TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            connection = psycopg.conninfo.conninfo_to_dict(dsn)
            database = DatabaseConnection.objects.create(
                name="Synthetic migration fixture",
                host=connection["host"],
                port=int(connection["port"]),
                database=connection["dbname"],
                username=role,
                secret=encrypt(password),
                sslmode=connection.get("sslmode", "disable"),
            )
            environment.database = database
            environment.save()
            request = Request.objects.create(
                environment=environment,
                analysis_protocol="2.4",
                need="Explain ordinary cancellation and its migration exception.",
                language="en",
            )
            enqueue_analysis(request.pk)
            source = committed_source
            values = [
                {
                    "status": "READY_TO_ANALYZE",
                    "understanding": "Explain cancellation conditions.",
                    "questions": [],
                    "ticket": None,
                    "complexity": "simple",
                },
                report(source),
                report(source, exception=True),
                {
                    "status": "APPROVED",
                    "summary": "Review the omitted migration branch.",
                    "issues": [],
                    "verification": None,
                },
                verification(source),
                bundle.model_dump(),
            ]
            capabilities = []
            failures = []

            def invoke_checked(path, payload, **kwargs):
                assert password not in payload["prompt"]
                has_database = bool(payload["database"])
                capabilities.append(has_database)
                with SkillResources(
                    payload["skill_definitions"], storage, payload["agent"], has_database
                ):
                    pass
                sql_skills = [
                    item
                    for item in payload["skill_definitions"]
                    if "read_database" in item.get("required_capabilities", [])
                ]
                assert bool(sql_skills) == has_database
                output = values.pop(0)
                receipts = []
                if payload["profile"] == "synthesis":
                    broker = Broker(
                        "codex",
                        {},
                        10,
                        database=lambda statement: query(
                            payload["database"], statement, minimize=True
                        ),
                    )
                    observed = broker.query_database(
                        f"SELECT count(*) AS counterexamples FROM {schema}.records WHERE migration AND cancelled AND ongoing"
                    )
                    assert observed["rows"] == [[1]]
                    receipts = broker.database_checks
                    claim = output["report"]["claims"][-1]
                    claim["sources"].append({"kind": "sql", "query_id": observed["query_id"]})
                    claim["scope"].update(
                        conditions=["The migration branch is used."],
                        period=observed["checked_at"],
                        population="Synthetic migration fixture rows",
                        sample_limits="Only two synthetic rows and the frozen function were checked.",
                    )
                    claim["counterexamples"] = [
                        {
                            "description": "One migrated fixture row is cancelled with ongoing benefits.",
                            "interpretation": "current_behavior",
                        }
                    ]
                return {
                    "output": output,
                    "database_checks": receipts,
                    "session_id": str(uuid.uuid4()),
                }

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
                for _ in range(8):
                    job = claim_job()
                    if job is None:
                        break
                    perform_job(job)
                    request.refresh_from_db()
                    if request.status in {"READY", "PARTIAL", "ERROR"}:
                        break
            assert request.status == "READY", (request.error, failures, capabilities)
            assert not values and capabilities == [False, True, True, True, True, False]
            evidence = request.versions.get().evidence
            assert evidence["database"]["status"] == "checked"
            assert len(evidence["database"]["checks"]) == 1
            assert evidence["claims"][-1]["counterexamples"]
            assert "rows" not in evidence["database"]["checks"][0]
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def evidence(source, id="ordinary", statement="Ongoing benefits block ordinary cancellations."):
    return {
        "id": id,
        "statement": statement,
        "kind": "observed",
        "status": "supported",
        "scope": {
            "environment": "Staging",
            "conditions": [
                "The migration branch of the inspected guard is used."
                if statement == EXCEPTION
                else "Blocking is enabled for ordinary contracts."
            ],
            "period": "The frozen source version",
            "population": "Inputs to the inspected cancellation guard",
            "sample_limits": "No other callers or live business records were checked.",
        },
        "sources": [source],
    }


def coverage(exception=False):
    return {
        "inspected_areas": ["Cancellation guard, blocking configuration and migration branch"],
        "new_elements": [
            {
                "id": "migration-branch",
                "kind": "omission",
                "description": EXCEPTION,
                "business_impact": "A rule covering every cancellation would be incomplete.",
                "claim_ids": ["migration"],
                "material": True,
            }
        ]
        if exception
        else [],
        "unexplored_zones": [],
    }


def report(source, workflow="request", exception=False):
    value = {
        "claims": [evidence(source)],
        "questions": [],
        "coverage": coverage(exception),
        "evidence": ["policy.py:can_cancel"],
    }
    if exception:
        value["claims"].append(evidence(source, "migration", EXCEPTION))
    if workflow == "question":
        value["observed_behavior"] = "The guard is conditional."
    else:
        value.update(
            current_behavior="The guard is conditional.",
            proposed_solution="State the applicable conditions.",
            impacts=["Cancellation scope"],
            database_impact="No changes",
            risks=[],
            tests_expected=["Check ordinary and migration contracts."],
            uncertainties=[],
        )
    return value


def verification(source, resolution=True):
    return {
        "report": {
            "claims": [
                evidence(source, "analyst:ordinary"),
                evidence(source, "counter:ordinary"),
                evidence(source, "counter:migration", EXCEPTION),
            ],
            "database": {"status": "not_configured"},
        },
        "questions": [],
        "coverage_resolutions": [
            {
                "finding_id": "counter:migration-branch",
                "status": "addressed",
                "notes": "The actual migration branch changes the scope of the ordinary rule.",
                "claim_ids": ["counter:migration"],
            }
        ]
        if resolution
        else [],
        "additional_omissions": [],
    }


def model_reports(source):
    return CoverageCodeReport(**report(source)), CoverageCodeReport(
        **report(source, exception=True)
    )


def qualifier():
    value = object.__new__(OmissionsOrchestrator)
    value.run = SimpleNamespace(
        orchestration={},
        context_snapshot={"business_decisions": {"decisions": []}},
        save=lambda **kwargs: None,
    )
    return value


def synthetic_source():
    return {
        "kind": "git",
        "repository": "company/backend",
        "commit": "a" * 40,
        "path": "policy.py",
        "line_start": 1,
        "line_end": 4,
        "excerpt": SOURCE.strip(),
    }


def test_v24_reports_require_explicit_inspected_and_unexplored_areas():
    source = synthetic_source()
    raw = report(source)
    del raw["coverage"]
    with pytest.raises(ValidationError):
        CoverageCodeReport(**raw)
    assert ReliableOrchestrator.protocol_version == "2.3"
    assert OmissionsOrchestrator.protocol_version == "2.4"
    assert (
        CoverageQuestionReport(**report(source, "question", True)).coverage.new_elements[0].kind
        == "omission"
    )


@pytest.mark.parametrize("resolution", ["missing", "unsupported_claim", "unverified"])
def test_true_initial_claims_do_not_waive_a_material_omission(resolution):
    source = synthetic_source()
    analyst, counter = model_reports(source)
    raw = verification(source, resolution != "missing")
    if resolution == "unsupported_claim":
        raw["coverage_resolutions"][0]["claim_ids"] = ["invented-claim"]
    elif resolution == "unverified":
        raw["coverage_resolutions"][0]["status"] = "unverified"
    reviewed = CoverageAssessment(**raw)
    checked = qualifier().qualify_coverage(reviewed.report, reviewed, analyst, counter)
    assert checked.blocking
    assert EXCEPTION in checked.limitations
    assert analyst.claims[0].status == "supported"


def test_addressed_omission_needs_a_supported_final_claim():
    source = synthetic_source()
    analyst, counter = model_reports(source)
    reviewed = CoverageAssessment(**verification(source))
    checked = qualifier().qualify_coverage(reviewed.report, reviewed, analyst, counter)
    assert not checked.blocking
    reviewed.report.claims[-1].status = "partial"
    assert qualifier().qualify_coverage(reviewed.report, reviewed, analyst, counter).blocking


def test_material_unexplored_area_cannot_disappear_from_review():
    source = synthetic_source()
    analyst, counter = model_reports(source)
    raw = counter.model_dump()
    raw["coverage"]["unexplored_zones"] = [
        {
            "id": "scheduler",
            "area": "Scheduled migration entry point",
            "reason": "Its caller may change cancellation behavior.",
        }
    ]
    counter = CoverageCodeReport.model_validate(raw)
    reviewed = CoverageAssessment(**verification(source))
    checked = qualifier().qualify_coverage(reviewed.report, reviewed, analyst, counter)
    assert checked.blocking and "Scheduled migration entry point" in checked.limitations


def test_many_coverage_limits_preserve_partial_result_and_full_audit():
    from core.reliable_flow import bound_report_limitations

    source = synthetic_source()
    analyst, counter = model_reports(source)
    reviewed = CoverageAssessment(**verification(source, False))
    reviewed.report.limitations = [f"Unverified area {index}" for index in range(30)]
    value = qualifier()
    checked = value.qualify_coverage(reviewed.report, reviewed, analyst, counter)
    assert checked.blocking
    assert len(checked.limitations) > 30
    complete = list(checked.limitations)
    bounded = bound_report_limitations(checked, value.run, "fr")
    assert bounded.blocking
    assert len(bounded.limitations) == 30
    assert value.run.orchestration["coverage"]["limitations"] == complete
    assert EXCEPTION in value.run.orchestration["coverage"]["unresolved"]
    assert "D’autres limites" in bounded.limitations[-1]
    type(bounded).model_validate(bounded.model_dump())


def test_verifier_discovers_an_essential_area_missed_by_both_explorations():
    source = synthetic_source()
    analyst = CoverageCodeReport(**report(source))
    counter = CoverageCodeReport(**report(source))
    raw = verification(source, False)
    raw["additional_omissions"] = [coverage(True)["new_elements"][0]]
    reviewed = CoverageAssessment(**raw)
    value = qualifier()
    checked = value.qualify_coverage(reviewed.report, reviewed, analyst, counter)
    assert checked.blocking and EXCEPTION in checked.limitations
    assert (
        value.run.orchestration["coverage"]["concerns"][0]["finding_id"]
        == "verifier:migration-branch"
    )


def test_unresolved_business_choice_requires_clarification_before_writing():
    source = synthetic_source()
    analyst, counter = model_reports(source)
    counter.coverage.new_elements.append(
        CoverageFinding(
            **{
                "id": "intended-exception",
                "kind": "business_decision",
                "description": "The desired migration exception is not confirmed.",
                "business_impact": "Ticket acceptance depends on whether migrated contracts can be cancelled.",
                "business_question": {
                    "id": "migration-rule",
                    "decision_key": "migration-rule",
                    "question": "What cancellation rule should apply to migrated contracts?",
                    "reason": "The existing migration path bypasses the ordinary guard.",
                },
            }
        )
    )
    reviewed = CoverageAssessment(**verification(source))
    checked = qualifier().qualify_coverage(reviewed.report, reviewed, analyst, counter)
    assert checked.blocking
    assert reviewed.questions[0].id == "migration-rule"
    with pytest.raises(ValidationError, match="user questions"):
        CoverageAssessment(
            **{
                **verification(source),
                "coverage_resolutions": [
                    {
                        "finding_id": "counter:intended-exception",
                        "status": "business_decision",
                        "notes": "A human must choose.",
                    }
                ],
            }
        )


@pytest.fixture
def committed_source(environment, storage):
    repository = storage / "company/backend"
    repository.mkdir(parents=True)
    (repository / "policy.py").write_text(SOURCE)
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
    source = synthetic_source()
    source["commit"] = git("-C", repository, "rev-parse", "HEAD")
    environment.repositories.update(sha=source["commit"])
    return source


@pytest.mark.django_db
@pytest.mark.parametrize(("workflow", "inferred_intent"), [
    ("request", "feature"), ("question", "question"), ("question", "mixed"),
])
@pytest.mark.parametrize("resolved", [True, False])
@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("with_diagrams", [False, True])
def test_independent_omission_is_carried_to_final_scoped_outputs(
    environment, storage, committed_source, bundle, workflow, resolved, automatic, inferred_intent, with_diagrams
):
    source = committed_source
    value = Request.objects.create(
        environment=environment,
        analysis_protocol="2.4",
        workflow="request" if automatic else workflow,
        intent_mode="auto" if automatic else "explicit",
        need="Explain cancellation and add manual review for migration cancellations." if with_diagrams else "Explain whether ongoing benefits block cancellation.",
        language="en",
    )
    enqueue_analysis(value.pk)
    final = (
        bundle.model_dump()
        if workflow == "request"
        else {
            "status": "READY",
            "answer": {
                "title": "Cancellation conditions",
                "summary": "The ordinary rule has a migration exception.",
            },
        }
    )
    values = [
        {
            "status": "READY_TO_ANALYZE",
            "understanding": "PRIVATE_REQUIREMENT_CODE_FINDING",
            "questions": [],
            "ticket": None,
            "complexity": "simple",
            "intent": inferred_intent,
        },
        {**report(source, workflow), "uncertainties": ["PRIVATE_INITIAL_ANALYST_FINDING"]},
        report(source, workflow, True),
        {
            "status": "APPROVED",
            "summary": "The ordinary claim is true but omits the migration exception.",
            "issues": [],
            "verification": None,
        },
        verification(source, resolved),
        final,
    ]
    if with_diagrams:
        values[0]["complexity"] = "complex"
        values[1]["diagrams"] = [{
            "id": "ordinary", "title": "Ordinary cancellation", "audience": "business", "kind": "decision",
            "purpose": "PRIVATE_DIAGRAM_FINDING", "alternative_text": "The ordinary cancellation path checks ongoing benefits.",
            "nodes": [{"id": "request", "label": "Cancellation request"}, {"id": "guard", "label": "Ordinary guard", "kind": "decision"}, {"id": "result", "label": "Cancellation decision"}],
            "edges": [{"id": "guard", "source": "request", "target": "guard", "label": "Ordinary path", "meaning": "existing", "claim_ids": ["ordinary"]},
                      {"id": "result", "source": "guard", "target": "result", "label": "Benefit check", "meaning": "existing", "claim_ids": ["ordinary"]}],
        }]
        values[2]["diagrams"] = [{
            "id": "exception", "title": "Migration path", "audience": "technical", "kind": "dependencies",
            "purpose": "Explain the omitted migration branch and the requested future review.", "alternative_text": "Migration imports currently bypass the ordinary guard. The proposed future path requires manual review before cancellation.",
            "nodes": [{"id": "request", "label": "Cancellation request"}, {"id": "migration", "label": "Migration path"}, {"id": "result", "label": "Cancellation allowed"}, {"id": "review", "label": "Manual review"}],
            "edges": [{"id": "migration", "source": "request", "target": "migration", "label": "Migration exception", "meaning": "existing", "claim_ids": ["migration"]},
                      {"id": "result", "source": "migration", "target": "result", "label": "Guard bypass", "meaning": "existing", "claim_ids": ["migration"]},
                      {"id": "review", "source": "migration", "target": "review", "label": "Require requested manual review", "meaning": "proposed"},
                      {"id": "reviewed", "source": "review", "target": "result", "label": "Continue after approval", "meaning": "proposed"}],
        }]
        values[4]["diagram_reviews"] = [
            {"diagram_id": role + ":" + graph["id"], "edge_id": edge["id"], "verdict": "supported",
             "notes": "This is the requested future change, not deployed behavior." if edge["meaning"] == "proposed" else "The relation follows the inspected branch at the frozen SHA."}
            for role, output in (("analyst", values[1]), ("counter", values[2]))
            for graph in output["diagrams"] for edge in graph["edges"]
        ]
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(copy.deepcopy(payload))
        assert values, "Unexpected provider invocation"
        return {"output": values.pop(0), "session_id": payload["session_id"] or str(uuid.uuid4())}

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        for _ in range(16):
            job = claim_job()
            if not job:
                break
            perform_job(job)
            value.refresh_from_db()
            if value.status in {"READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"}:
                break
    value.refresh_from_db()
    assert value.status == ("READY" if resolved else "PARTIAL"), value.error
    assert value.workflow == workflow
    assert len(calls) == 6 and not values
    counter = next(call for call in calls if call["profile"] == "independent")
    assert "PRIVATE_REQUIREMENT_CODE_FINDING" in calls[1]["prompt"]
    assert "PRIVATE_INITIAL_ANALYST_FINDING" not in counter["prompt"]
    assert "PRIVATE_REQUIREMENT_CODE_FINDING" not in counter["prompt"]
    assert "PRIVATE_DIAGRAM_FINDING" not in counter["prompt"]
    assert value.need in counter["prompt"]
    assert "OMISSION DISCOVERY POLICY" in counter["prompt"]
    assert counter["context_id"] != calls[1]["context_id"]
    verifier = next(call for call in calls if call["profile"] == "synthesis")
    assert "counter:migration-branch" in verifier["prompt"]
    assert "essential areas missed by both" in verifier["prompt"]
    version = value.versions.get()
    assert any(row["id"] == "counter:migration" for row in version.evidence["claims"])
    assert version.evidence["blocking"] is not resolved
    assert len(version.evidence["diagrams"]) == (2 if with_diagrams else 0)
    for artifact in version.artifacts.all():
        assert EXCEPTION in artifact.content
        assert source["commit"] in artifact.content
        assert ("```mermaid" in artifact.content) == (with_diagrams and artifact.name != "ticket.md")
        if with_diagrams and artifact.name != "ticket.md":
            assert "Proposed change" in artifact.content and "Existing" in artifact.content
    assert value.analysis_runs.get().orchestration["coverage"]["concerns"][0]["kind"] == "omission"


def migration_question():
    options = []
    for key, label, behavior in (
        ("a", "Keep the ordinary guard", "Block migrated cancellations with ongoing benefits."),
        ("b", "Keep the migration exception", "Allow the existing migration exception."),
    ):
        options.append(
            {
                "id": key,
                "label": label,
                "behavior": behavior,
                "relevance": "Use when this is the intended treatment of migrated contracts.",
                "benefits": "Makes the chosen cancellation rule explicit.",
                "limitations": "The other policy will not apply.",
                "consequences": "Migrated cases follow the selected cancellation policy.",
            }
        )
    return {
        "id": "migration-rule",
        "decision_key": "migration-rule",
        "kind": "choice",
        "question": "What cancellation rule should apply to migrated contracts?",
        "reason": "The migration path bypasses the ordinary guard.",
        "options": options,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("workflow", ["request", "question"])
def test_omitted_business_exception_clarifies_then_reuses_validated_explorations(
    client, environment, storage, committed_source, bundle, workflow
):
    source = committed_source
    value = Request.objects.create(
        environment=environment,
        analysis_protocol="2.4",
        workflow=workflow,
        need="Explain which cancellation rule is intended.",
        language="en",
    )
    enqueue_analysis(value.pk)
    initial_job = value.analysis_runs.get().job_id
    counter = report(source, workflow, True)
    question = migration_question()
    counter["coverage"]["new_elements"].append(
        {
            "id": "intended-rule",
            "kind": "business_decision",
            "description": "The intended migration rule is unconfirmed.",
            "business_impact": "Ticket acceptance depends on treatment of migrated contracts.",
            "business_question": question,
        }
    )
    review = verification(source)
    review["coverage_resolutions"].append(
        {
            "finding_id": "counter:intended-rule",
            "status": "business_decision",
            "notes": "The user must choose the intended migration rule.",
        }
    )
    review["questions"] = [question]
    values = [
        {
            "status": "READY_TO_ANALYZE",
            "understanding": "Explain cancellation intent.",
            "questions": [],
            "ticket": None,
            "complexity": "simple",
        },
        report(source, workflow),
        counter,
        {
            "status": "APPROVED",
            "summary": "Send the independently discovered issue to verification.",
            "issues": [],
            "verification": None,
        },
        review,
    ]
    calls = []

    def invoke(path, payload, **kwargs):
        calls.append(copy.deepcopy(payload))
        assert values, "A clarification must not invoke the writer"
        return {"output": values.pop(0), "session_id": payload["session_id"] or str(uuid.uuid4())}

    def process_until_waiting():
        for _ in range(16):
            job = claim_job()
            if not job:
                break
            perform_job(job)
            value.refresh_from_db()
            if value.status in {"READY", "PARTIAL", "ERROR", "NEEDS_CLARIFICATION"}:
                break

    with (
        patch("core.worker.request_workspace", return_value=storage),
        patch("core.worker.runtime_call", side_effect=invoke),
    ):
        process_until_waiting()
        assert value.status == "NEEDS_CLARIFICATION", value.error
        assert not value.versions.exists() and len(calls) == 5
        assert claim_job() is None
        base = "questions" if workflow == "question" else "requests"
        answer = "Allow migration cancellation only after manual review."
        response = client.post(
            f"/api/{base}/{value.pk}/answers",
            {
                "choices": {"migration-rule": {"option_id": "other", "text": answer}},
                "expected_decision_revision": 0,
            },
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        resumed = verification(source)
        resumed["coverage_resolutions"].append(
            {
                "finding_id": "counter:intended-rule",
                "status": "addressed",
                "notes": "The explicit human answer establishes the intended migration policy.",
                "decision_keys": ["migration-rule"],
            }
        )
        final = (
            bundle.model_dump()
            if workflow == "request"
            else {
                "status": "READY",
                "answer": {
                    "title": "Migration cancellation",
                    "summary": "The chosen migration rule applies.",
                },
            }
        )
        values.extend([resumed, final])
        process_until_waiting()
    assert value.status == "READY", value.error
    assert value.analysis_runs.count() == 1
    assert value.analysis_runs.get().job_id == initial_job
    assert [row["profile"] for row in calls[5:]] == ["synthesis", "writer"]
    assert all(answer in row["prompt"] for row in calls[5:])
    for artifact in value.versions.get().artifacts.all():
        assert answer in artifact.content
