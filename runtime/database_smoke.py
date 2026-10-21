"""Exercise the sandbox's DB capability against an explicitly disposable PostgreSQL."""

import logging
import os
import secrets
import threading
import time

import httpx
import psycopg
import uvicorn
from psycopg import sql

from . import workflow_smoke


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    dsn = os.environ["SPECHELPER_SMOKE_POSTGRES_DSN"]
    password = secrets.token_urlsafe(32)
    role = "spechelper_fixture_reader"
    server = uvicorn.Server(
        uvicorn.Config("runtime.server:app", host="127.0.0.1", port=8090, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    with psycopg.connect(dsn, autocommit=True) as db:
        # No pre-existing objects are removed: accidentally targeting a populated test
        # instance fails before the fixture can alter existing data.
        db.execute("CREATE SCHEMA spechelper_fixture")
        try:
            db.execute("CREATE TABLE spechelper_fixture.contracts (id int, name text)")
            db.execute("INSERT INTO spechelper_fixture.contracts VALUES (1, 'Active')")
            db.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            try:
                db.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA spechelper_fixture TO {}").format(
                        sql.Identifier(role)
                    )
                )
                db.execute(
                    sql.SQL("GRANT SELECT ON spechelper_fixture.contracts TO {}").format(
                        sql.Identifier(role)
                    )
                )
                connection = psycopg.conninfo.conninfo_to_dict(dsn)
                thread.start()
                deadline = time.monotonic() + 10
                while not server.started:
                    if not thread.is_alive() or time.monotonic() >= deadline:
                        raise RuntimeError("Temporary query service did not start")
                    time.sleep(0.05)
                workflow_smoke.main(
                    {
                        "host": connection["host"],
                        "port": int(connection.get("port", 5432)),
                        "database": connection.get("dbname", "postgres"),
                        "username": role,
                        "password": password,
                        "sslmode": "disable",
                    }
                )
                assert db.execute("SELECT * FROM spechelper_fixture.contracts").fetchall() == [
                    (1, "Active")
                ]
                assert (
                    httpx.post(
                        "http://127.0.0.1:8090/query/unknown", json={"sql": "SELECT 1"}
                    ).status_code
                    == 403
                )
            finally:
                server.should_exit = True
                if thread.ident:
                    thread.join(timeout=10)
                db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        finally:
            db.execute("DROP SCHEMA spechelper_fixture CASCADE")


if __name__ == "__main__":
    main()
