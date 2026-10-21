import psycopg
from pglast import ast, parse_sql

from .secrets import decrypt


def parameters(connection):
    return {
        "host": connection.host,
        "port": connection.port,
        "dbname": connection.database,
        "user": connection.username,
        "password": decrypt(connection.secret),
        "sslmode": connection.sslmode,
        "connect_timeout": 5,
        "options": "-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000",
    }


def check_role(cursor):
    cursor.execute("""
        SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
        FROM pg_roles WHERE rolname = current_user
    """)
    if cursor.fetchone()[0]:
        raise ValueError("The PostgreSQL role must be read-only")
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname NOT IN ('pg_catalog','information_schema')
            AND c.relkind IN ('r','p','v','m','f')
            AND (has_table_privilege(c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
                 OR has_any_column_privilege(c.oid, 'INSERT,UPDATE')
                 OR pg_has_role(c.relowner, 'USAGE'))
        ) OR EXISTS (
            SELECT 1 FROM pg_namespace WHERE nspname !~ '^pg_'
            AND nspname <> 'information_schema' AND has_schema_privilege(oid, 'CREATE')
        ) OR has_database_privilege(current_database(), 'CREATE')
    """)
    if cursor.fetchone()[0]:
        raise ValueError("The role has write or create privileges")


def check_connection(connection):
    try:
        with psycopg.connect(**parameters(connection)) as db:
            db.read_only = True
            with db.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise ValueError("The read query failed")
                check_role(cursor)
    except psycopg.Error as exc:
        raise ValueError("Could not connect to PostgreSQL") from exc
    return True


def validate_query(sql):
    try:
        statements = parse_sql(sql)
    except Exception as exc:
        raise ValueError("Invalid SQL") from exc
    if len(statements) != 1 or not isinstance(statements[0].stmt, ast.SelectStmt):
        raise ValueError("Only one SELECT query is allowed")
    # Reject SELECT INTO, data-modifying CTEs, locks and side-effecting functions.
    from pglast.visitors import Visitor

    class ReadOnly(Visitor):
        def visit(self, ancestors, node):
            if isinstance(node, (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt, ast.MergeStmt)):
                raise ValueError("Writes are forbidden")
            if isinstance(node, ast.SelectStmt) and (node.intoClause or node.lockingClause):
                raise ValueError("Writes and locking are forbidden")
            if isinstance(node, ast.FuncCall):
                name = ".".join(part.sval for part in node.funcname).lower()
                allowed = {
                    "count",
                    "sum",
                    "avg",
                    "min",
                    "max",
                    "coalesce",
                    "nullif",
                    "lower",
                    "upper",
                    "length",
                    "substring",
                    "date_trunc",
                    "extract",
                    "round",
                    "abs",
                    "jsonb_typeof",
                    "jsonb_array_length",
                    "array_length",
                    "string_agg",
                }
                if name not in allowed:
                    raise ValueError("SQL function not allowed")

    ReadOnly()(statements)


def query(config, sql):
    validate_query(sql)
    try:
        with psycopg.connect(**config) as db:
            db.read_only = True
            with db.cursor() as cursor:
                check_role(cursor)
                cursor.execute(sql)
                rows = cursor.fetchmany(201)
                return {
                    "columns": [column.name for column in cursor.description],
                    "rows": rows[:200],
                    "truncated": len(rows) > 200,
                }
    except psycopg.Error as exc:
        raise ValueError("Query rejected or unavailable") from exc
