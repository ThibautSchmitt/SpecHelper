"""Run with SPECHELPER_TEST_POSTGRES_DSN against a disposable database only."""

import os

import psycopg
import pytest

from core.postgres import check_role, query

DSN = os.environ.get("SPECHELPER_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL not configured")


@pytest.fixture
def readonly_config():
    with psycopg.connect(DSN, autocommit=True) as db:
        db.execute("DROP SCHEMA IF EXISTS fixture CASCADE")
        db.execute("DROP ROLE IF EXISTS fixture_reader")
        db.execute("CREATE SCHEMA fixture")
        db.execute("CREATE TABLE fixture.contracts (id int, name text)")
        db.execute("INSERT INTO fixture.contracts VALUES (1,'Active')")
        db.execute("CREATE ROLE fixture_reader LOGIN PASSWORD 'fixture-test-only'")
        db.execute("GRANT CONNECT ON DATABASE postgres TO fixture_reader")
        db.execute("GRANT USAGE ON SCHEMA fixture TO fixture_reader")
        db.execute("GRANT SELECT ON ALL TABLES IN SCHEMA fixture TO fixture_reader")
    config = psycopg.conninfo.conninfo_to_dict(DSN)
    config.update(
        user="fixture_reader",
        password="fixture-test-only",
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
    )
    yield config
    with psycopg.connect(DSN, autocommit=True) as db:
        db.execute("DROP SCHEMA fixture CASCADE")
        db.execute("DROP OWNED BY fixture_reader")
        db.execute("DROP ROLE fixture_reader")


def test_real_role_and_transaction_enforcement(readonly_config):
    result = query(readonly_config, "SELECT id, name FROM fixture.contracts")
    assert result["rows"] == [(1, "Active")]
    with psycopg.connect(**readonly_config) as db:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            db.execute("DELETE FROM fixture.contracts")
    with psycopg.connect(DSN) as db, db.cursor() as cursor:
        with pytest.raises(ValueError, match="read-only"):
            check_role(cursor)
    with psycopg.connect(DSN, autocommit=True) as db:
        db.execute("GRANT UPDATE ON fixture.contracts TO fixture_reader")
    with pytest.raises(ValueError, match="write"):
        query(readonly_config, "SELECT * FROM fixture.contracts")

    with psycopg.connect(DSN, autocommit=True) as db:
        db.execute("REVOKE UPDATE ON fixture.contracts FROM fixture_reader")
        db.execute("GRANT UPDATE(name) ON fixture.contracts TO fixture_reader")
    with pytest.raises(ValueError, match="write"):
        query(readonly_config, "SELECT * FROM fixture.contracts")


@pytest.mark.django_db
def test_real_database_url_probe_rejects_writer_and_returns_three_checks(
    client, storage, readonly_config
):
    import json
    from urllib.parse import quote

    config = readonly_config
    url = f"postgresql://{quote(config['user'])}:{quote(config['password'])}@{config['host']}:{config.get('port', 5432)}/{config.get('dbname', 'postgres')}?sslmode=disable"
    response = client.post(
        "/api/connections/databases",
        data=json.dumps({"name": "Real read-only probe", "url": url}),
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["checks"] == {"connection": True, "read": True, "read_only": True}
    assert set(response.json()) == {"id", "name", "status", "checks"}
    with psycopg.connect(DSN, autocommit=True) as db:
        db.execute("GRANT UPDATE ON fixture.contracts TO fixture_reader")
    refused = client.post(f"/api/connections/databases/{response.json()['id']}/test")
    assert refused.status_code == 422
    assert config["password"] not in refused.content.decode()
