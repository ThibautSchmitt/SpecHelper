import re

import psycopg
from pglast import ast, parse_sql

from .secrets import decrypt
from .ticket_urls import transport_host


def parameters(connection):
    return {
        "host": transport_host(connection.host),
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


SENSITIVE_COLUMN = re.compile(
    r"(?i)(?:^|_)(?:name|nom|prenom|email|mail|phone|telephone|mobile|address|adresse|password|secret|token|ssn|nir|iban|birth|dob|customer_id|person_id)(?:$|_)"
)


SCHEMA_NAMES = {
    "column_name",
    "table_name",
    "table_schema",
    "schema_name",
    "constraint_name",
    "udt_name",
}


def schema_metadata_query(sql):
    """Names of columns/tables are not personal record values."""
    from pglast.visitors import Visitor

    relations = []

    class Relations(Visitor):
        def visit_RangeVar(self, ancestors, node):
            relations.append((node.schemaname, node.relname))

    Relations()(parse_sql(sql))
    return bool(relations) and all(
        schema == "information_schema"
        and table
        in {
            "columns",
            "tables",
            "schemata",
            "table_constraints",
            "key_column_usage",
            "constraint_column_usage",
        }
        for schema, table in relations
    )


def sensitive_projections(sql, *, safe_columns=()):
    """Follow sensitive projection aliases, including CTEs and expressions.

    Conservative name-based protection supplements database column provenance;
    it is not a general semantic personal-data classifier. Counts remain useful.
    """
    from pglast.visitors import Visitor

    targets = []

    def projected_targets(query):
        if not isinstance(query, ast.SelectStmt):
            return []
        return list(query.targetList or projected_targets(query.larg))

    def renamed_targets(query, names):
        for target, name in zip(projected_targets(query), names or ()):
            targets.append(ast.ResTarget(name=name.sval, val=target.val))

    class Targets(Visitor):
        def visit_ResTarget(self, ancestors, node):
            targets.append(node)

        def visit_CommonTableExpr(self, ancestors, node):
            renamed_targets(node.ctequery, node.aliascolnames)

        def visit_RangeSubselect(self, ancestors, node):
            if node.alias:
                renamed_targets(node.subquery, node.alias.colnames)

        def visit_SelectStmt(self, ancestors, node):
            # UNION/INTERSECT/EXCEPT expose the left-hand column names even
            # when a right-hand expression selects sensitive content.
            if node.larg and node.rarg:
                for left, right in zip(projected_targets(node.larg), projected_targets(node.rarg)):
                    name = left.name
                    if not name and isinstance(left.val, ast.ColumnRef):
                        name = getattr(left.val.fields[-1], "sval", None)
                    if name:
                        targets.append(ast.ResTarget(name=name, val=right.val))

    Targets()(parse_sql(sql))
    aliases = set()

    class References(Visitor):
        def __init__(self):
            super().__init__()
            self.sensitive = False

        def visit_ColumnRef(self, ancestors, node):
            names = [part.sval for part in node.fields if isinstance(part, ast.String)]
            if names and (
                (names[-1].lower() not in safe_columns and SENSITIVE_COLUMN.search(names[-1]))
                or names[-1].lower() in aliases
            ):
                # count(person_id) reveals cardinality, not personal identifiers.
                parents, current = [], ancestors
                while current is not None:
                    if isinstance(current.node, ast.FuncCall):
                        parents.append(current.node)
                    current = current.parent
                if not any(
                    ".".join(p.sval for p in parent.funcname).lower() == "count"
                    for parent in parents
                ):
                    self.sensitive = True

    for _ in range(len(targets) + 1):
        before = set(aliases)
        for target in targets:
            visitor = References()
            visitor(target.val)
            if visitor.sensitive:
                if target.name:
                    aliases.add(target.name.lower())
                elif isinstance(target.val, ast.ColumnRef):
                    names = [p.sval for p in target.val.fields if isinstance(p, ast.String)]
                    if names:
                        aliases.add(names[-1].lower())
                elif isinstance(target.val, ast.FuncCall):
                    aliases.add(target.val.funcname[-1].sval.lower())
                else:
                    aliases.add("?column?")
        if aliases == before:
            break
    return aliases


def minimize_result(result, *, sensitive_columns=(), safe_columns=()):
    """Expose a small bounded preview; aggregates and anonymous state values are preferred."""
    rows, size = [], 0
    redacted = False
    for row in result["rows"][:20]:
        values = []
        for column, value in zip(result["columns"], row, strict=True):
            if value is not None and (
                (column.lower() not in safe_columns and SENSITIVE_COLUMN.search(column))
                or column.lower() in sensitive_columns
            ):
                value, redacted = "[REDACTED]", True
            elif isinstance(value, (str, bytes)):
                text = value.decode(errors="replace") if isinstance(value, bytes) else value
                scrubbed = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED]", text)
                scrubbed = re.sub(
                    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,})",
                    "[REDACTED]",
                    scrubbed,
                )
                redacted |= scrubbed != text or len(scrubbed) > 160
                value = scrubbed[:160]
            elif isinstance(value, (dict, list, tuple)):
                value, redacted = "[STRUCTURED VALUE OMITTED]", True
            values.append(value)
        size += len(str(values))
        if size > 16000:
            break
        rows.append(values)
    return {
        **result,
        "rows": rows,
        "truncated": result["truncated"] or len(rows) < len(result["rows"]),
        "minimized": True,
        "redacted": redacted,
        "observed_row_count": len(result["rows"]),
        "limitations": "At most 20 rows and bounded cells are exposed. Sensitive-looking fields are masked. Prefer counts, existence checks and grouped states; this preview is not a universal or exhaustive check.",
    }


def audit_sql(sql):
    """Normalize a validated query without storing literal business values or comments."""
    from pglast.stream import RawStream

    normalized = RawStream()(parse_sql(sql))
    normalized = re.sub(r"'(?:''|[^'])*'", "'?'", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "?", normalized)
    return normalized[:20000]


def query(config, sql, *, minimize=False):
    validate_query(sql)
    try:
        with psycopg.connect(**config) as db:
            db.read_only = True
            with db.cursor() as cursor:
                check_role(cursor)
                cursor.execute(sql)
                rows = cursor.fetchmany(201)
                result = {
                    "columns": [column.name for column in cursor.description],
                    "rows": rows[:200],
                    "truncated": len(rows) > 200,
                }
                if minimize:
                    safe = SCHEMA_NAMES if schema_metadata_query(sql) else set()
                    return minimize_result(
                        result,
                        sensitive_columns=sensitive_projections(sql, safe_columns=safe),
                        safe_columns=safe,
                    )
                return result
    except psycopg.Error as exc:
        raise ValueError("Query rejected or unavailable") from exc
