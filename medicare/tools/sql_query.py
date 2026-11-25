"""Sandboxed SQLite query tool with read-only enforcement, authorizer, and timeout."""

import asyncio
import os
import re
import sqlite3
import time
from typing import Any

from pydantic import BaseModel

from medicare.config import settings
from medicare.domain.errors import EmptyDatabaseError, SQLExecutionError
from medicare.domain.models import SQLAttempt, TableResult
from medicare.tools.base import BaseTool
from medicare.tools.db_tools import format_schema_documentation, get_live_schema


class SQLExecutionTraceResult(BaseModel):
    """Result of execute_query_with_trace containing attempt metrics."""

    attempt: SQLAttempt
    success: bool
    table: TableResult | None = None
    error: str | None = None


ALLOWED_FUNCTIONS = {
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "round",
    "abs",
    "lower",
    "upper",
    "coalesce",
    "ifnull",
    "length",
    "substr",
    "trim",
    "replace",
    "cast",
    "typeof",
    "instr",
    "like",
    "printf",
    "date",
    "datetime",
    "strftime",
    "nullif",
}


def _sanitize_error_message(msg: str) -> str:
    """Strip filesystem paths from error messages."""
    return re.sub(r"(/[a-zA-Z0-9_\-.]+)+", "[REDACTED_PATH]", msg)


def _classify_sql_error(err_str: str) -> str:
    """Classify SQLite error into kind: syntax | no_such_table | no_such_column | forbidden | timeout | other."""
    err_lower = err_str.lower()
    if (
        "not authorized" in err_lower
        or "access denied" in err_lower
        or "forbidden" in err_lower
        or "prohibited" in err_lower
    ):
        return "forbidden"
    if "interrupted" in err_lower or "timed out" in err_lower or "progress handler" in err_lower:
        return "timeout"
    if "no such table" in err_lower:
        return "no_such_table"
    if "no such column" in err_lower:
        return "no_such_column"
    if "syntax error" in err_lower or "near " in err_lower or "incomplete input" in err_lower:
        return "syntax"
    return "other"


class SQLiteQueryTool(BaseTool):
    """Secure, read-only SQLite execution tool for hospital & procedure records."""

    name = "hospital_sql"
    description = "Execute a single read-only SELECT query against the hospital directory and procedural cost database."
    ACTIVE_DB_PATH: str | None = None

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path
        if db_path:
            SQLiteQueryTool.ACTIVE_DB_PATH = db_path
        self.timeout_seconds = getattr(settings, "SQL_TIMEOUT_SECONDS", 5.0)
        self.max_rows = getattr(settings, "SQL_MAX_ROWS", 200)

    @property
    def db_path(self) -> str:
        return self._db_path or settings.MEDICARE_DB_PATH

    @db_path.setter
    def db_path(self, val: str) -> None:
        self._db_path = val

    def _check_db_validity(self) -> None:
        """Ensure DB file exists and has rows."""
        if not os.path.exists(self.db_path):
            raise EmptyDatabaseError(
                "Hospital database file not found. Run 'python -m medicare.medicare.setup --all' to initialize."
            )
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            schema = get_live_schema(self.db_path)
            check_tables = schema.get("exposed_tables", [])
            total_rows = 0
            for table in check_tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                total_rows += cursor.fetchone()[0]
            conn.close()
            if total_rows == 0:
                raise EmptyDatabaseError(
                    "Hospital database exists but contains 0 records. Import seed data with 'python -m medicare.medicare.setup --all'."
                )
        except sqlite3.OperationalError as e:
            raise EmptyDatabaseError(f"Database access failed: {_sanitize_error_message(str(e))}")

    def get_schema(self) -> str:
        """Introspect tables, columns, sample rows, and append documentation."""
        schema = get_live_schema(self.db_path)
        if schema and schema.get("tables"):
            return format_schema_documentation(schema)
        return ""

    def _sync_run(self, query: str) -> TableResult:
        """Synchronous query runner with strict sandboxing."""
        self._check_db_validity()

        cleaned_query = query.strip()
        # Strip trailing semicolon
        if cleaned_query.endswith(";"):
            cleaned_query = cleaned_query[:-1].strip()

        # Reject multiple statements
        if ";" in cleaned_query:
            raise SQLExecutionError(
                "Multiple statements are strictly forbidden. Only a single SELECT query is allowed.",
                kind="forbidden",
            )

        # Must start with SELECT or WITH
        first_token = cleaned_query.split()[0].upper() if cleaned_query.split() else ""
        if first_token not in ("SELECT", "WITH"):
            raise SQLExecutionError(
                f"Forbidden statement type '{first_token}'. Only SELECT or WITH statements are allowed.",
                kind="forbidden",
            )

        start_time = time.monotonic()
        timeout = self.timeout_seconds

        def progress_handler() -> int:
            if time.monotonic() - start_time > timeout:
                return 1  # Abort query
            return 0

        schema = get_live_schema(self.db_path)
        live_tables = set(schema.get("exposed_tables", []))
        allowed_tables = live_tables
        live_cols = schema.get("exposed_columns", {})
        allowed_cols_map = {t.lower(): {c.lower() for c in cols} for t, cols in live_cols.items()}

        def authorizer(
            action_code: int, param1: Any, param2: Any, dbname: Any, trigger_name: Any
        ) -> int:
            if action_code == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action_code == sqlite3.SQLITE_READ:
                # param1: table name, param2: column name
                table = param1.lower() if param1 else None
                col = param2.lower() if param2 else None
                if table:
                    if table not in allowed_tables:
                        return sqlite3.SQLITE_DENY
                    if col and col not in allowed_cols_map.get(table, set()):
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            if action_code == sqlite3.SQLITE_FUNCTION:
                func = param2.lower() if param2 else None
                if func and func in ALLOWED_FUNCTIONS:
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_DENY

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.set_authorizer(authorizer)
            conn.set_progress_handler(progress_handler, 100)
            cursor = conn.cursor()

            cursor.execute(cleaned_query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            fetched = cursor.fetchmany(self.max_rows + 1)
            conn.close()

            # Deduplicate exact duplicate rows while preserving order
            seen_rows: set[tuple[Any, ...]] = set()
            unique_fetched: list[list[Any]] = []
            for r in fetched:
                r_tuple = tuple(r)
                if r_tuple not in seen_rows:
                    seen_rows.add(r_tuple)
                    unique_fetched.append(list(r))

            truncated = len(unique_fetched) > self.max_rows
            rows = unique_fetched[: self.max_rows]

            return TableResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
            )
        except sqlite3.OperationalError as e:
            raw_msg = _sanitize_error_message(str(e))
            kind = _classify_sql_error(raw_msg)
            raise SQLExecutionError(raw_msg, kind=kind) from e
        except sqlite3.DatabaseError as e:
            raw_msg = _sanitize_error_message(str(e))
            kind = _classify_sql_error(raw_msg)
            raise SQLExecutionError(raw_msg, kind=kind) from e
        except Exception as e:
            if isinstance(e, (SQLExecutionError, EmptyDatabaseError)):
                raise
            raw_msg = _sanitize_error_message(str(e))
            raise SQLExecutionError(raw_msg, kind="other") from e

    def run(self, query: str) -> TableResult:
        """Run SQL query synchronously."""
        return self._sync_run(query)

    async def execute_query_with_trace(
        self, query: str, attempt_index: int = 1
    ) -> SQLExecutionTraceResult:
        """Execute query asynchronously and return structured trace result."""
        start = time.monotonic()
        try:
            table = await asyncio.to_thread(self._sync_run, query)
            (time.monotonic() - start) * 1000.0
            attempt = SQLAttempt(
                attempt=attempt_index,
                sql=query,
                row_count=table.row_count,
            )
            return SQLExecutionTraceResult(attempt=attempt, success=True, table=table)
        except SQLExecutionError as e:
            (time.monotonic() - start) * 1000.0
            attempt = SQLAttempt(
                attempt=attempt_index,
                sql=query,
                error=str(e),
                kind=e.kind or _classify_sql_error(str(e)),
                row_count=0,
            )
            return SQLExecutionTraceResult(attempt=attempt, success=False, error=str(e))
        except Exception as e:
            (time.monotonic() - start) * 1000.0
            attempt = SQLAttempt(
                attempt=attempt_index,
                sql=query,
                error=str(e),
                kind=_classify_sql_error(str(e)),
                row_count=0,
            )
            return SQLExecutionTraceResult(attempt=attempt, success=False, error=str(e))

    async def execute(self, query: str = "", **kwargs: Any) -> str:
        """Execute SQL query asynchronously and return JSON representation or error string."""
        q = query or kwargs.get("sql", "")
        try:
            result = await asyncio.to_thread(self._sync_run, q)
            return result.model_dump_json()
        except Exception as e:
            kind = getattr(e, "kind", _classify_sql_error(str(e)))
            return f"SQL Error ({kind}): {e}"

    def to_schema(self) -> dict[str, Any]:
        """Return function calling schema descriptor."""
        return {
            "type": "function",
            "function": {
                "name": "run_sql",
                "description": (
                    "Execute a single read-only SQLite SELECT query against the hospital directory "
                    "and procedural cost database."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A single read-only SQLite SELECT statement",
                        }
                    },
                    "required": ["query"],
                },
            },
        }
