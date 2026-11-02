"""Connection editing never exposes a stored secret or skips the reader check."""

import json

import pytest

from core.models import DatabaseConnection, Environment, Job, Request, ResultVersion
from core.secrets import decrypt, encrypt

pytestmark = pytest.mark.django_db


@pytest.fixture
def database():
    return DatabaseConnection.objects.create(name="Fixture reader", host="db.example", port=5432,
        database="business", username="reader", secret=encrypt("fixture-old-password"),
        sslmode="require", status="CONNECTED")


def payload(database, **changes):
    return {"name":database.name, "host":database.host, "port":database.port,
            "database":database.database, "username":database.username, "sslmode":database.sslmode,
            "password":"", **changes}


def endpoint(database):
    return f"/api/connections/databases/{database.pk}"


def test_edit_preserves_blank_password_and_environment_associations(client, database, monkeypatch):
    environment = Environment.objects.create(name="Attached environment", database=database)
    original_secret = database.secret
    checked = []
    monkeypatch.setattr("core.api.check_connection", lambda connection: checked.append((connection.host, decrypt(connection.secret))))
    response = client.put(endpoint(database), payload(database, name="Renamed reader", host="new-db.example"), content_type="application/json")
    assert response.status_code == 200, response.content
    database.refresh_from_db()
    environment.refresh_from_db()
    assert database.name == "Renamed reader" and database.host == "new-db.example"
    assert database.secret == original_secret and environment.database_id == database.pk
    assert checked == [("new-db.example", "fixture-old-password")]
    assert response.json()["checks"] == {"connection":True, "read":True, "read_only":True}
    assert "fixture-old-password" not in response.content.decode()


def test_edit_url_replaces_password_without_disclosing_it(client, database, monkeypatch):
    checked = []
    monkeypatch.setattr("core.api.check_connection", lambda connection: checked.append((connection.host, connection.username, decrypt(connection.secret))))
    response = client.put(endpoint(database), payload(database, host="", username="", url="postgresql://next_reader:fixture-next-password@next-db.example:5433/next_business?sslmode=verify-full"), content_type="application/json")
    assert response.status_code == 200, response.content
    database.refresh_from_db()
    assert checked == [("next-db.example", "next_reader", "fixture-next-password")]
    assert (database.port, database.database, database.sslmode) == (5433, "next_business", "verify-full")
    public = client.get("/api/connections").json()["databases"]
    assert not any("secret" in row or "password" in row for row in public)
    assert "fixture-next-password" not in json.dumps(public) + response.content.decode()


def test_failed_proposed_connection_does_not_replace_the_saved_configuration(client, database, monkeypatch):
    original = payload(database)
    def refuse(connection):
        raise ValueError("The PostgreSQL role must be read-only")
    monkeypatch.setattr("core.api.check_connection", refuse)
    response = client.put(endpoint(database), payload(database, host="unverified.example", password="fixture-rejected-password"), content_type="application/json")
    assert response.status_code == 422
    database.refresh_from_db()
    assert payload(database) == original and database.status == "CONNECTED"
    assert decrypt(database.secret) == "fixture-old-password"
    assert "fixture-rejected-password" not in response.content.decode()


def test_duplicates_and_invalid_urls_are_refused_before_testing(client, database, monkeypatch):
    DatabaseConnection.objects.create(name="Existing reader", host="other", database="other", username="reader", secret=encrypt("fixture-other-password"))
    monkeypatch.setattr("core.api.check_connection", lambda connection: pytest.fail("Invalid input must not open a database connection"))
    assert client.put(endpoint(database), payload(database, name="Existing reader"), content_type="application/json").status_code == 409
    assert client.put(endpoint(database), payload(database, url="http://adminer.example"), content_type="application/json").status_code == 422
    assert client.put(endpoint(database), payload(database, url="postgresql://reader@host/database?options=-c%20transaction_read_only=off"), content_type="application/json").status_code == 422
    assert client.post("/api/connections/databases", payload(database, name="Missing password"), content_type="application/json").status_code == 422


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING"])
def test_edit_cannot_redirect_an_active_analysis(client, database, monkeypatch, status):
    environment = Environment.objects.create(name="Busy environment", database=database)
    request = Request.objects.create(environment=environment, need="Inspect the current records")
    Job.objects.create(kind="discussion", target=str(request.pk), status=status)
    monkeypatch.setattr("core.api.check_connection", lambda connection: pytest.fail("No probe while a dependent analysis is active"))
    assert client.put(endpoint(database), payload(database, host="different.example"), content_type="application/json").status_code == 409
    database.refresh_from_db()
    assert database.host == "db.example"


@pytest.mark.parametrize("reference", ["environment", "request", "version"])
def test_delete_preserves_environment_and_history_references(client, database, reference):
    if reference == "environment":
        Environment.objects.create(name="Attached environment", database=database)
    elif reference == "request":
        Request.objects.create(need="Historical question", database_snapshot={"id":database.pk, "name":database.name})
    else:
        request = Request.objects.create(need="Question with an older database")
        ResultVersion.objects.create(request=request, number=1, database_snapshot={"id":database.pk})
    assert client.delete(endpoint(database)).status_code == 409
    assert DatabaseConnection.objects.filter(pk=database.pk).exists()


def test_delete_unused_configuration_does_not_contact_the_business_database(client, database, monkeypatch):
    monkeypatch.setattr("core.api.check_connection", lambda connection: pytest.fail("Deletion only removes application configuration"))
    assert client.delete(endpoint(database)).json() == {"deleted":True}
    assert not DatabaseConnection.objects.filter(pk=database.pk).exists()


def test_failed_saved_connection_test_persists_its_real_error_state(client, database, monkeypatch):
    def fail(connection):
        raise ValueError("Could not connect to PostgreSQL")
    monkeypatch.setattr("core.api.check_connection", fail)
    assert client.post(endpoint(database) + "/test").status_code == 422
    database.refresh_from_db()
    assert database.status == "ERROR"
