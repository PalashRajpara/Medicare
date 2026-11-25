"""Test verifying that the MediCare Navigator pipeline works dynamically with arbitrary second datasets."""

import sqlite3

import pytest

from medicare.medicare.dataset.schema import ALL_DDL_STATEMENTS
from medicare.medicare.graph.build import build_navigator_graph
from medicare.medicare.graph.deps import Dependencies
from medicare.tools.sql_query import SQLiteQueryTool


@pytest.fixture
def invented_dataset_db(tmp_path):
    """Fixture initializing an invented second dataset (Atlantis, Gotham, etc.)."""
    db_file = str(tmp_path / "invented_healthcare.db")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    for stmt in ALL_DDL_STATEMENTS:
        cursor.executescript(stmt)

    # Insert invented hospital records
    cursor.execute(
        "INSERT INTO hospitals (hospital_id, name, city, state, rating, bed_count, nabh_accredited, emergency_wait_minutes) "
        "VALUES (101, 'Poseidon Medical Center', 'Atlantis', 'Oceanic', 4.8, 350, 1, 15);"
    )
    cursor.execute(
        "INSERT INTO hospital_procedures (procedure_id, hospital_id, procedure_name, category, min_cost_inr, max_cost_inr, avg_cost_inr, avg_wait_days, room_rent_per_day_inr) "
        "VALUES (201, 101, 'Hyperbaric Chamber Therapy', 'Marine Medicine', 40000, 80000, 60000, 2, 5000);"
    )
    cursor.execute(
        "INSERT INTO insurer_acceptance (acceptance_id, hospital_id, insurer_name, cashless_accepted, network_type, avg_claim_settlement_days) "
        "VALUES (301, 101, 'Neptune Shield Insurance', 1, 'Tier-1', 3);"
    )
    conn.commit()
    conn.close()
    return db_file


@pytest.mark.asyncio
async def test_invented_dataset_end_to_end(invented_dataset_db):
    """Verify MediCare Navigator works end-to-end on completely invented domain data with zero code modifications."""
    deps = Dependencies.default()
    deps.sql_tool = SQLiteQueryTool(db_path=invented_dataset_db)

    graph = build_navigator_graph(deps)

    question = "Compare Hyperbaric Chamber Therapy costs in Atlantis"
    initial_state = {
        "question": question,
        "history": [],
        "user_id": "test_user_atlantis",
        "doc_scope": "both",
    }

    result = await graph.ainvoke(
        initial_state, config={"configurable": {"thread_id": "test_invented_thread"}}
    )

    assert result is not None
    assert "answer" in result
    assert result.get("guardrail") is not None
    assert not result["guardrail"].blocked

    # Verify SQL result picked up the invented hospital records
    sql_res = result.get("sql_result")
    assert sql_res is not None
    assert sql_res.success is True
    assert sql_res.table is not None
    assert sql_res.table.row_count > 0

    # Ensure invented values appear in retrieved table
    found_city = any("Atlantis" in str(row) for row in sql_res.table.rows)
    found_proc = any("Hyperbaric Chamber Therapy" in str(row) for row in sql_res.table.rows)
    assert found_city, "Invented city 'Atlantis' was not found in SQL results."
    assert found_proc, (
        "Invented procedure 'Hyperbaric Chamber Therapy' was not found in SQL results."
    )


@pytest.mark.asyncio
async def test_adding_new_row_updates_answers_with_zero_code_changes(invented_dataset_db):
    """Demonstrate that inserting a new row dynamically updates results with zero code changes."""
    deps = Dependencies.default()
    deps.sql_tool = SQLiteQueryTool(db_path=invented_dataset_db)

    # Insert a new procedure row into live database
    conn = sqlite3.connect(invented_dataset_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO hospital_procedures (procedure_id, hospital_id, procedure_name, category, min_cost_inr, max_cost_inr, avg_cost_inr, avg_wait_days, room_rent_per_day_inr) "
        "VALUES (202, 101, 'Bionic Spine Alignment', 'Advanced Cybernetics', 150000, 300000, 225000, 5, 8000);"
    )
    conn.commit()
    conn.close()

    graph = build_navigator_graph(deps)
    question = "Show Bionic Spine Alignment at Poseidon Medical Center"
    result = await graph.ainvoke(
        {"question": question, "user_id": "test_dynamic_row"},
        config={"configurable": {"thread_id": "test_dynamic_row_thread"}},
    )

    sql_res = result.get("sql_result")
    assert sql_res is not None
    assert sql_res.success is True
    found_bionic = any("Bionic Spine Alignment" in str(row) for row in sql_res.table.rows)
    assert found_bionic, "Newly added procedure was not dynamically retrieved."
