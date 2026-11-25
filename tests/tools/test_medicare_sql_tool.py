"""Security and execution tests for SQLiteQueryTool."""

import sqlite3

import pytest

from medicare.domain.errors import EmptyDatabaseError, SQLExecutionError
from medicare.medicare.dataset.csv_import import import_all_csvs
from medicare.medicare.dataset.schema import ALL_DDL_STATEMENTS
from medicare.tools.sql_query import SQLiteQueryTool


@pytest.fixture
def populated_db(tmp_path):
    """Fixture initializing temporary SQLite database with test fixtures."""
    db_file = str(tmp_path / "test_hospitals.db")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    for stmt in ALL_DDL_STATEMENTS:
        cursor.executescript(stmt)
    conn.commit()
    conn.close()

    seed_dir = "tests/fixtures/medicare/seed"
    import_all_csvs(seed_dir=seed_dir, db_path=db_file)
    return db_file


def test_empty_database_error_when_missing(tmp_path):
    missing_path = str(tmp_path / "non_existent.db")
    tool = SQLiteQueryTool(db_path=missing_path)
    with pytest.raises(EmptyDatabaseError):
        tool.run("SELECT * FROM hospitals")


def test_empty_database_error_when_zero_rows(tmp_path):
    empty_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(empty_path)
    for stmt in ALL_DDL_STATEMENTS:
        conn.cursor().executescript(stmt)
    conn.commit()
    conn.close()

    tool = SQLiteQueryTool(db_path=empty_path)
    with pytest.raises(EmptyDatabaseError):
        tool.run("SELECT * FROM hospitals")


def test_valid_select_query_execution(populated_db):
    tool = SQLiteQueryTool(db_path=populated_db)
    result = tool.run(
        "SELECT h.name AS hospital_name, h.city, p.procedure_name, p.avg_cost_inr "
        "FROM hospitals h JOIN hospital_procedures p ON h.hospital_id = p.hospital_id "
        "WHERE lower(h.city) = 'ahmedabad' ORDER BY p.avg_cost_inr ASC"
    )
    assert result.row_count > 0
    assert "hospital_name" in result.columns
    assert result.truncated is False


def test_reject_destructive_dml_statements(populated_db):
    tool = SQLiteQueryTool(db_path=populated_db)
    forbidden_queries = [
        "DROP TABLE hospitals",
        "DELETE FROM hospitals",
        "UPDATE hospitals SET name = 'Hacked'",
        "INSERT INTO hospitals (hospital_id, name, city, state) VALUES (99, 'Fake', 'Surat', 'Gujarat')",
        "ALTER TABLE hospitals ADD COLUMN fake TEXT",
        "PRAGMA table_info(hospitals)",
    ]
    for q in forbidden_queries:
        with pytest.raises(SQLExecutionError) as exc_info:
            tool.run(q)
        assert exc_info.value.kind in ("forbidden", "syntax", "other")


def test_reject_stacked_statements(populated_db):
    tool = SQLiteQueryTool(db_path=populated_db)
    stacked = "SELECT * FROM hospitals; SELECT * FROM hospital_procedures;"
    with pytest.raises(SQLExecutionError) as exc_info:
        tool.run(stacked)
    assert exc_info.value.kind == "forbidden"
    assert "multiple statements" in exc_info.value.message.lower()


def test_reject_sqlite_master_access(populated_db):
    tool = SQLiteQueryTool(db_path=populated_db)
    with pytest.raises(SQLExecutionError) as exc_info:
        tool.run("SELECT sql FROM sqlite_master WHERE type='table'")
    assert exc_info.value.kind == "forbidden"


def test_disallowed_sql_function_rejected(populated_db):
    tool = SQLiteQueryTool(db_path=populated_db)
    # randomblob or hex is not in ALLOWED_FUNCTIONS
    with pytest.raises(SQLExecutionError) as exc_info:
        tool.run("SELECT randomblob(16) FROM hospitals")
    assert exc_info.value.kind == "forbidden"


def test_read_only_connection_enforced(populated_db):
    """Ensure opening file in read-only mode prevents writes at OS/SQLite level."""
    # Attempt direct write on read-only URI
    with pytest.raises(sqlite3.OperationalError):
        conn = sqlite3.connect(f"file:{populated_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE rogue_table (id INT)")
        conn.close()


def test_row_cap_enforcement(populated_db):
    tool = SQLiteQueryTool(db_path=populated_db)
    tool.max_rows = 2
    res = tool.run("SELECT * FROM hospital_procedures")
    assert res.row_count == 2
    assert res.truncated is True
