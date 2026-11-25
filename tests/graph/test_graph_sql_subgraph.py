"""Tests for self-correcting Hospital SQL sub-graph."""

import pytest

from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.sql_subgraph import build_sql_graph
from medicare.providers.mock_engine import ScriptedProvider


def test_sql_subgraph_compiles_and_nodes_exist():
    """Verify SQL sub-graph compiles and contains all lifecycle nodes."""
    graph = build_sql_graph()
    node_names = set(graph.get_graph().nodes.keys())
    for n in [
        "load_schema",
        "generate_sql",
        "static_check",
        "execute_sql",
        "fix_sql",
        "broaden_query",
        "finish",
        "give_up",
    ]:
        assert n in node_names


@pytest.mark.asyncio
async def test_sql_subgraph_retry_flow_and_bounded_attempts():
    """Verify that bad SQL is repaired within bounded retry attempts."""
    deps = Dependencies.default()
    provider = ScriptedProvider(
        responses=[
            "SELECT non_existent_column FROM hospitals",
            "SELECT hospital_id, name, city FROM hospitals LIMIT 10",
        ]
    )
    deps.provider = provider
    graph = build_sql_graph(deps)

    res = await graph.ainvoke({"question": "Show hospitals", "attempts": [], "retry_count": 0})

    assert res.get("success") is True
    assert len(res.get("attempts", [])) == 2
    assert res["attempts"][0].error is not None
    assert res["attempts"][1].error is None


@pytest.mark.asyncio
async def test_sql_subgraph_static_check_rejects_before_execution():
    """Verify static check flags forbidden query without DB execution."""
    deps = Dependencies.default()
    provider = ScriptedProvider(
        responses=[
            "DROP TABLE hospitals",
            "SELECT hospital_id, name FROM hospitals LIMIT 5",
        ]
    )
    deps.provider = provider
    graph = build_sql_graph(deps)

    res = await graph.ainvoke({"question": "Drop hospitals", "attempts": [], "retry_count": 0})

    assert len(res["attempts"]) >= 2
    assert res["attempts"][0].kind == "forbidden"
    assert "DROP" in res["attempts"][0].error
