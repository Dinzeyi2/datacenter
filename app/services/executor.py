import time
import json
from typing import Any
from sqlalchemy import create_engine, text
from app.models.connection import DBConnection

ALLOWED_STATEMENT_TYPES = ("select", "with", "explain")
MAX_ROWS = 5000


def _build_url(conn: DBConnection, password: str) -> str:
    if conn.db_type == "postgres":
        return f"postgresql://{conn.username}:{password}@{conn.host}:{conn.port}/{conn.database}"
    elif conn.db_type == "mysql":
        return f"mysql+pymysql://{conn.username}:{password}@{conn.host}:{conn.port}/{conn.database}"
    elif conn.db_type == "sqlite":
        return f"sqlite:///{conn.database}"
    raise ValueError(f"Unsupported db_type: {conn.db_type}")


def _is_safe(sql: str) -> bool:
    stripped = sql.strip().lower()
    return any(stripped.startswith(t) for t in ALLOWED_STATEMENT_TYPES)


def substitute_variables(sql: str, variables: dict) -> str:
    for key, value in variables.items():
        sql = sql.replace(f"{{{{{key}}}}}", str(value))
    return sql


def run_query(conn: DBConnection, decrypted_password: str, sql: str) -> dict[str, Any]:
    if not _is_safe(sql):
        raise PermissionError("Only SELECT / WITH / EXPLAIN statements are allowed.")

    url = _build_url(conn, decrypted_password)
    engine = create_engine(url, connect_args={"connect_timeout": 10})

    start = time.time()
    with engine.connect() as connection:
        result = connection.execute(text(sql))
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchmany(MAX_ROWS)]
    elapsed_ms = (time.time() - start) * 1000

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "execution_time_ms": round(elapsed_ms, 2),
        "truncated": len(rows) == MAX_ROWS,
    }


def get_schema(conn: DBConnection, decrypted_password: str) -> list[dict]:
    url = _build_url(conn, decrypted_password)
    engine = create_engine(url, connect_args={"connect_timeout": 10})

    with engine.connect() as c:
        if conn.db_type == "postgres":
            tables_result = c.execute(text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('pg_catalog','information_schema') "
                "ORDER BY table_schema, table_name"
            ))
            tables = [(r[0], r[1]) for r in tables_result]
            schema_data = []
            for schema, table in tables:
                cols_result = c.execute(text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema=:s AND table_name=:t ORDER BY ordinal_position"
                ), {"s": schema, "t": table})
                columns = [{"name": r[0], "type": r[1]} for r in cols_result]
                schema_data.append({"schema": schema, "table": table, "columns": columns})
            return schema_data

        elif conn.db_type == "mysql":
            tables_result = c.execute(text(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() ORDER BY table_name"
            ))
            tables = [(r[0], r[1]) for r in tables_result]
            schema_data = []
            for schema, table in tables:
                cols_result = c.execute(text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema=:s AND table_name=:t ORDER BY ordinal_position"
                ), {"s": schema, "t": table})
                columns = [{"name": r[0], "type": r[1]} for r in cols_result]
                schema_data.append({"schema": schema, "table": table, "columns": columns})
            return schema_data

        elif conn.db_type == "sqlite":
            tables_result = c.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ))
            tables = [r[0] for r in tables_result]
            schema_data = []
            for table in tables:
                cols_result = c.execute(text(f"PRAGMA table_info({table})"))
                columns = [{"name": r[1], "type": r[2]} for r in cols_result]
                schema_data.append({"schema": "main", "table": table, "columns": columns})
            return schema_data

    return []
