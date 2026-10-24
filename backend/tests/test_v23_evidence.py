"""Actual provenance, limited observations and minimized business data."""

import os
from types import SimpleNamespace

import psycopg
import pytest

from core.analysis_evidence import GitSource, check_report, checked_git_source
from core.git import run as git
from core.postgres import audit_sql, minimize_result, query
from runtime.broker import Broker


@pytest.fixture
def provenance(tmp_path):
    repository = tmp_path / "company/backend"
    repository.mkdir(parents=True)
    (repository / "rules.py").write_text("def allowed(active):\n    return active\n")
    git("init", repository)
    git("-C", repository, "add", "rules.py")
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
    sha = git("-C", repository, "rev-parse", "HEAD")
    baseline = [{"repository": "company/backend", "sha": sha}]
    source = dict(
        kind="git",
        repository="company/backend",
        commit=sha,
        path="rules.py",
        line_start=1,
        line_end=2,
        excerpt="def allowed(active):\n    return active",
    )
    return tmp_path, repository, baseline, source


def test_git_requires_exact_commit_content_lines_and_baseline(provenance):
    workspace, repository, baseline, source = provenance
    assert checked_git_source(GitSource(**source), baseline, workspace)
    assert not checked_git_source(
        GitSource(**{**source, "excerpt": "invented"}), baseline, workspace
    )
    assert not checked_git_source(GitSource(**{**source, "commit": "a" * 40}), baseline, workspace)
    (repository / "rules.py").write_text(
        source["excerpt"] + "\n# Modified outside the cited lines\n"
    )
    assert not checked_git_source(GitSource(**source), baseline, workspace)


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", ".git/config", "nested/../secret"])
def test_source_rejects_paths_outside_source_files(provenance, path):
    with pytest.raises(ValueError):
        GitSource(**{**provenance[3], "path": path})


def report(source, **claim_overrides):
    return {
        "claims": [
            {
                "id": "analyst:active",
                "statement": "Active records are accepted under the inspected conditions.",
                "kind": "observed",
                "status": "supported",
                "scope": {
                    "period": "Frozen source version",
                    "conditions": ["Active flag is true"],
                    "population": "Inspected function inputs",
                    "sample_limits": "Only the cited implementation was inspected",
                },
                "sources": [source],
                **claim_overrides,
            }
        ],
        "database": {"status": "checked"},
    }


@pytest.fixture
def context(provenance):
    workspace, _, baseline, source = provenance
    request = SimpleNamespace(
        database_snapshot={},
        baseline=baseline,
        environment_name_snapshot="Staging",
        environment_id=None,
    )
    run = SimpleNamespace(orchestration={}, context_snapshot={"dossier": {"baseline": baseline}})
    return workspace, source, request, run


@pytest.mark.django_db
def test_actual_git_support_and_absent_database_are_separate(context):
    workspace, source, request, run = context
    checked = check_report(report(source), request, run, workspace)
    assert checked.claims[0].status == "supported"
    assert checked.database.status == "not_configured"
    assert not checked.blocking


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [
        ("period", ""),
        ("environment", "Another environment"),
        ("conditions", [" "]),
        ("population", " "),
        ("sample_limits", "\t"),
    ],
)
def test_incomplete_scope_or_mismatched_environment_blocks_unqualified_support(
    context, field, value
):
    workspace, source, request, run = context
    value_report = report(source)
    value_report["claims"][0]["scope"][field] = value
    checked = check_report(value_report, request, run, workspace)
    assert checked.claims[0].status == "partial"
    assert checked.blocking
    assert checked.claims[0].scope.environment == "Staging"


@pytest.mark.django_db
def test_invented_query_receipt_never_confirms_business_data(context):
    workspace, _, request, run = context
    request.database_snapshot = {"configured": True}
    checked = check_report(report({"kind": "sql", "query_id": "invented"}), request, run, workspace)
    assert checked.database.status == "not_checked"
    assert checked.claims[0].status == "unverified" and checked.blocking
    assert checked.claims[0].sources == []


@pytest.mark.django_db
def test_actual_receipt_keeps_counterexample_and_historical_limits(context):
    workspace, _, request, run = context
    broker = Broker(
        "codex",
        {},
        10,
        database=lambda sql: {"columns": ["exception_count"], "rows": [[3]], "truncated": False},
    )
    observation = broker.query_database(
        "SELECT count(*) AS exception_count FROM historical_records WHERE active = false"
    )
    request.database_snapshot = {"configured": True}
    run.orchestration["database_checks"] = broker.database_checks
    checked = check_report(
        report(
            {"kind": "sql", "query_id": observation["query_id"]},
            universal=True,
            counterexamples=[
                {
                    "description": "Three historical exceptions exist",
                    "interpretation": "historical_anomaly",
                }
            ],
        ),
        request,
        run,
        workspace,
    )
    assert checked.database.status == "checked"
    assert checked.claims[0].status == "contradicted" and checked.blocking
    assert checked.claims[0].counterexamples[0].description == "Three historical exceptions exist"
    assert "historical anomaly" in checked.claims[0].verification_notes
    assert "rows" not in checked.database.checks[0].model_dump()


def test_broker_receipts_minimize_literals_and_distinguish_failures():
    broker = Broker(
        "codex",
        {},
        10,
        database=lambda sql: {"columns": ["count"], "rows": [[0]], "truncated": False},
    )
    observation = broker.query_database(
        "SELECT count(*) FROM records WHERE email = 'private@example.invalid' AND id=987 -- private comment"
    )
    receipt = broker.database_checks[0]
    assert observation["rows"] == [[0]] and receipt["status"] == "checked"
    assert "private" not in receipt["sql"] and "987" not in receipt["sql"]
    with pytest.raises(ValueError):
        broker.query_database("DELETE FROM records")
    assert broker.database_checks[-1]["status"] == "rejected"
    broker.database = lambda sql: (_ for _ in ()).throw(ValueError("private connection details"))
    with pytest.raises(ValueError, match="Read-only query rejected or unavailable"):
        broker.query_database("SELECT 1")
    assert broker.database_checks[-1]["status"] == "unavailable"


def test_minimized_results_keep_aggregates_but_mask_personal_data():
    result = minimize_result(
        {
            "columns": ["name", "email", "count", "note"],
            "rows": [("Alice", "private@example.invalid", 3, "x" * 1000)] * 30,
            "truncated": False,
        }
    )
    assert result["observed_row_count"] == 30 and result["truncated"]
    assert len(result["rows"]) <= 20
    assert result["rows"][0][:3] == ["[REDACTED]", "[REDACTED]", 3]
    assert len(result["rows"][0][3]) <= 161
    assert "private" not in audit_sql("SELECT 'private@example.invalid'::text")


@pytest.mark.django_db
def test_unqualified_universal_wording_is_not_saved_as_certainty(context):
    workspace, source, request, run = context
    checked = check_report(
        report(source, statement="This works in all cases.", universal=False),
        request,
        run,
        workspace,
    )
    assert checked.claims[0].universal
    assert checked.claims[0].status == "partial" and checked.blocking


@pytest.mark.skipif(
    not os.environ.get("SPECHELPER_TEST_POSTGRES_DSN"),
    reason="Disposable PostgreSQL not configured",
)
def test_real_readonly_counterexample_count_is_audited_without_private_rows():
    dsn = os.environ["SPECHELPER_TEST_POSTGRES_DSN"]
    role = "v23_evidence_reader"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute("CREATE SCHEMA v23_evidence_fixture")
        try:
            admin.execute(
                "CREATE TABLE v23_evidence_fixture.records (email text, current_allowed bool, historical bool)"
            )
            admin.execute(
                "INSERT INTO v23_evidence_fixture.records VALUES ('private@example.invalid',false,true), ('other@example.invalid',true,false)"
            )
            admin.execute("CREATE ROLE v23_evidence_reader LOGIN PASSWORD 'fixture-only-evidence'")
            try:
                admin.execute("GRANT USAGE ON SCHEMA v23_evidence_fixture TO v23_evidence_reader")
                admin.execute("GRANT SELECT ON v23_evidence_fixture.records TO v23_evidence_reader")
                config = psycopg.conninfo.conninfo_to_dict(dsn)
                config.update(user=role, password="fixture-only-evidence")
                broker = Broker(
                    "codex", {}, 10, database=lambda sql: query(config, sql, minimize=True)
                )
                observation = broker.query_database(
                    "SELECT count(*) AS counterexamples FROM v23_evidence_fixture.records WHERE historical AND NOT current_allowed"
                )
                assert observation["rows"] == [[1]]
                assert broker.database_checks[0]["status"] == "checked"
                preview = broker.query_database("SELECT email FROM v23_evidence_fixture.records")
                assert preview["rows"] == [["[REDACTED]"], ["[REDACTED]"]]
                assert "private" not in str(broker.database_checks)
                empty = broker.query_database(
                    "SELECT count(*) FROM v23_evidence_fixture.records WHERE historical AND current_allowed"
                )
                assert empty["rows"] == [[0]]
                with pytest.raises(ValueError):
                    broker.query_database(
                        "UPDATE v23_evidence_fixture.records SET current_allowed=true"
                    )
                assert admin.execute(
                    "SELECT count(*) FROM v23_evidence_fixture.records WHERE NOT current_allowed"
                ).fetchone() == (1,)
            finally:
                admin.execute("DROP OWNED BY v23_evidence_reader")
                admin.execute("DROP ROLE v23_evidence_reader")
        finally:
            admin.execute("DROP SCHEMA v23_evidence_fixture CASCADE")
