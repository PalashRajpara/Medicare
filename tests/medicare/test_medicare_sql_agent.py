"""Tests for HospitalSQLAgent self-correcting retry loop and ScriptedProvider test double."""

import sqlite3

import pytest

from medicare.agents.hospital_sql_agent import run_sql_loop
from medicare.medicare.dataset.csv_import import import_all_csvs
from medicare.medicare.dataset.schema import ALL_DDL_STATEMENTS
from medicare.providers.mock_engine import ScriptedProvider
from medicare.runtime.context import ExecutionContext
from medicare.tools.sql_query import SQLiteQueryTool


@pytest.fixture
def populated_db(tmp_path):
    db_file = str(tmp_path / "test_sql_agent.db")
    conn = sqlite3.connect(db_file)
    for stmt in ALL_DDL_STATEMENTS:
        conn.cursor().executescript(stmt)
    conn.commit()
    conn.close()
    import_all_csvs(seed_dir="tests/fixtures/medicare/seed", db_path=db_file)
    return db_file


@pytest.mark.asyncio
async def test_bad_first_sql_fixed_on_retry(populated_db):
    """Verify that a faulty initial query is auto-corrected on retry 1."""
    tool = SQLiteQueryTool(db_path=populated_db)
    ctx = ExecutionContext(thread_id="test-retry-1", run_id="r1", model="mock-model")

    # ScriptedProvider: 1st call fails with invalid column, 2nd call fixes it
    provider = ScriptedProvider(
        responses=[
            "SELECT hospital_id, non_existent_col FROM hospitals",  # Attempt 1 -> fails
            "SELECT hospital_id, name, city FROM hospitals",  # Attempt 2 (Fix 1) -> succeeds
        ]
    )

    emitted_events = []

    async def emit_status(node: str, payload: dict):
        emitted_events.append({"node": node, **payload})

    result = await run_sql_loop(
        question="Show hospitals",
        ctx=ctx,
        emit=emit_status,
        provider=provider,
        sql_tool=tool,
    )

    assert result.success is True
    assert len(result.attempts) == 2
    assert result.attempts[0].error is not None
    assert result.attempts[0].kind == "no_such_column"
    assert result.attempts[1].error is None

    # Check retry SSE event
    retry_events = [e for e in emitted_events if e.get("status") == "retry"]
    assert len(retry_events) == 1
    assert retry_events[0]["retry"] == 1
    assert retry_events[0]["max_retries"] == 3


@pytest.mark.asyncio
async def test_max_retries_exhaustion(populated_db):
    """Verify that after 1 initial + 3 retries (4 total executions), the loop stops with success=False."""
    tool = SQLiteQueryTool(db_path=populated_db)
    ctx = ExecutionContext(thread_id="test-exhaust", run_id="r2", model="mock-model")

    # Provider returns 4 consecutive failing queries
    provider = ScriptedProvider(
        responses=[
            "SELECT invalid_col_1 FROM hospitals",
            "SELECT invalid_col_2 FROM hospitals",
            "SELECT invalid_col_3 FROM hospitals",
            "SELECT invalid_col_4 FROM hospitals",
        ]
    )

    retry_counts = []

    async def emit_status(node: str, payload: dict):
        if payload.get("status") == "retry":
            retry_counts.append(payload.get("retry"))

    result = await run_sql_loop(
        question="Show hospitals",
        ctx=ctx,
        emit=emit_status,
        provider=provider,
        sql_tool=tool,
    )

    assert result.success is False
    assert len(result.attempts) == 4  # 1 initial + 3 fix attempts
    assert retry_counts == [1, 2, 3]


@pytest.mark.asyncio
async def test_repeated_identical_sql_detection(populated_db):
    """Verify that if the fixer returns the exact same failed query, it is detected and varied."""
    tool = SQLiteQueryTool(db_path=populated_db)
    ctx = ExecutionContext(thread_id="test-repeat", run_id="r3", model="mock-model")

    same_bad_sql = "SELECT bogus_col FROM hospitals"
    working_sql = "SELECT name, city FROM hospitals"

    provider = ScriptedProvider(
        responses=[
            same_bad_sql,  # Attempt 1 -> fails
            same_bad_sql,  # Fixer 1 repeats same bad sql -> variation prompted
            working_sql,  # Varied fix succeeds
        ]
    )

    result = await run_sql_loop(
        question="Show hospitals",
        ctx=ctx,
        provider=provider,
        sql_tool=tool,
    )

    assert result.success is True
    assert result.final_sql == working_sql
