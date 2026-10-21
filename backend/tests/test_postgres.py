import pytest

from core.postgres import validate_query


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT count(*) FROM contracts",
        "WITH active AS (SELECT id FROM contracts) SELECT * FROM active",
        "SELECT table_name FROM information_schema.tables",
        "SELECT lower(name), max(id) FROM contracts GROUP BY name",
    ],
)
def test_read_queries_allowed(sql):
    validate_query(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM contracts",
        "UPDATE contracts SET name='x'",
        "CREATE TABLE hacked(id int)",
        "SELECT 1; DELETE FROM contracts",
        "SELECT * INTO new_table FROM contracts",
        "WITH gone AS (DELETE FROM contracts RETURNING *) SELECT * FROM gone",
        "SELECT * FROM contracts FOR UPDATE",
        "SELECT pg_sleep(100)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT nextval('sequence')",
        "SELECT set_config('transaction_read_only','off',false)",
        "SELECT dblink_exec('foo','DELETE FROM contracts')",
    ],
)
def test_writes_and_side_effecting_functions_rejected(sql):
    with pytest.raises(ValueError):
        validate_query(sql)
