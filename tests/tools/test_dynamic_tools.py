"""Tests for dynamic discovery tools: get_schema, lookup_values, run_sql, and list_document_filters."""

import os
import sqlite3
import time

import pytest

from medicare.domain.errors import SQLExecutionError
from medicare.medicare.dataset.csv_import import import_all_csvs
from medicare.medicare.dataset.schema import ALL_DDL_STATEMENTS
from medicare.providers.mock_engine import ScriptedProvider
from medicare.tools.db_tools import (
    GetSchemaTool,
    ListDocumentFiltersTool,
    LookupValuesTool,
    get_live_schema,
)
from medicare.tools.sql_query import SQLiteQueryTool


@pytest.fixture
def temp_db(tmp_path):
    """Fixture initializing temporary SQLite database with test fixtures."""
    db_file = str(tmp_path / "test_dynamic.db")
    conn = sqlite3.connect(db_file)
    for stmt in ALL_DDL_STATEMENTS:
        conn.cursor().executescript(stmt)
    conn.commit()
    conn.close()

    seed_dir = "tests/fixtures/medicare/seed"
    import_all_csvs(seed_dir=seed_dir, db_path=db_file)
    return db_file


@pytest.mark.asyncio
async def test_get_schema_introspects_and_caches(temp_db):
    """Verify get_schema inspects tables, sample rows, and refreshes upon mtime change."""
    tool = GetSchemaTool(db_path=temp_db)
    schema_text = await tool.execute()

    assert "Table: hospitals" in schema_text
    assert "Table: hospital_procedures" in schema_text
    assert "Table: insurer_acceptance" in schema_text
    assert "Sample Rows" in schema_text

    # Verify hidden tables are not present
    assert "sqlite_sequence" not in schema_text

    # Test cache mtime invalidation
    initial_schema = get_live_schema(temp_db)
    assert "hospitals" in initial_schema["tables"]

    # Modify database file and add a new table
    time.sleep(0.05)
    conn = sqlite3.connect(temp_db)
    conn.execute("CREATE TABLE test_extra (id INTEGER PRIMARY KEY, note TEXT);")
    conn.commit()
    conn.close()

    # Touch file to ensure mtime advances
    new_mtime = os.path.getmtime(temp_db) + 2.0
    os.utime(temp_db, (new_mtime, new_mtime))

    refreshed_schema = get_live_schema(temp_db)
    assert "test_extra" in refreshed_schema["tables"]


@pytest.mark.asyncio
async def test_lookup_values_fuzzy_and_rejection(temp_db):
    """Verify lookup_values performs exact, substring, and fuzzy matching, and rejects unexposed columns."""
    tool = LookupValuesTool(db_path=temp_db)

    # 1. Substring match
    res_str = await tool.execute(table="hospitals", column="city", text="ahmed")
    assert "Ahmedabad" in res_str

    # 2. Fuzzy match
    res_fuzzy = await tool.execute(table="hospitals", column="city", text="Ahmdabad")
    assert "Ahmedabad" in res_fuzzy

    # 3. Reject non-existent or hidden column
    res_hidden = await tool.execute(table="hospitals", column="password_hash", text="secret")
    assert (
        "Error:" in res_hidden
        or "not accessible" in res_hidden.lower()
        or "hidden" in res_hidden.lower()
    )


@pytest.mark.asyncio
async def test_run_sql_dynamic_allowlist(temp_db):
    """Verify run_sql dynamically derives its allowlist from the live schema."""
    sql_tool = SQLiteQueryTool(db_path=temp_db)

    # Query exposed table succeeds
    res = sql_tool.run("SELECT name, city FROM hospitals LIMIT 2")
    assert res.row_count > 0

    # Querying sqlite_master is denied
    with pytest.raises(SQLExecutionError):
        sql_tool.run("SELECT name FROM sqlite_master")


@pytest.mark.asyncio
async def test_list_document_filters(temp_db):
    """Verify list_document_filters returns available insurers from database and manifest."""
    tool = ListDocumentFiltersTool(db_path=temp_db)
    res_str = await tool.execute()
    import json

    data = json.loads(res_str)
    assert "insurers" in data
    assert isinstance(data["insurers"], list)
    assert len(data["insurers"]) > 0


@pytest.mark.asyncio
async def test_scripted_provider_chat_loop():
    """Verify ScriptedProvider chat method supports tool calls and text generation."""
    provider = ScriptedProvider(
        responses=[
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "name": "lookup_values",
                        "arguments": {"table": "hospitals", "column": "city", "text": "city"},
                    }
                ],
            },
            {
                "content": "Final synthesis based on tool results.",
                "tool_calls": [],
            },
        ]
    )

    # Turn 1
    resp1 = await provider.chat(messages=[{"role": "user", "content": "Hello"}])
    assert len(resp1["tool_calls"]) == 1
    assert resp1["tool_calls"][0]["name"] == "lookup_values"

    # Turn 2
    resp2 = await provider.chat(
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "tool_calls": resp1["tool_calls"]},
            {"role": "tool", "tool_call_id": "tc_1", "content": '["TestCity"]'},
        ]
    )
    assert resp2["content"] == "Final synthesis based on tool results."
    assert len(resp2["tool_calls"]) == 0
