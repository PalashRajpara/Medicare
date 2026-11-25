"""Builder compiling the self-correcting Hospital SQL Agent sub-graph."""

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from medicare.config import settings
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.nodes_sql import (
    SQLSubState,
    broaden_query_node,
    execute_sql_node,
    finish_node,
    fix_sql_node,
    generate_sql_node,
    give_up_node,
    load_schema_node,
    static_check_node,
)


def route_after_static_check(state: SQLSubState) -> str:
    """Decide whether to proceed to execute or jump to fix/give_up."""
    if state.get("static_check_failed"):
        if len(state.get("attempts", [])) >= (1 + settings.SQL_MAX_RETRIES):
            return "give_up"
        return "fix_sql"
    return "execute_sql"


def route_after_execute(state: SQLSubState) -> str:
    """Evaluate SQL execution outcome (success, 0-row broaden, or error retry)."""
    if state.get("success"):
        table = state.get("table")
        # Check if 0 rows returned and not yet broadened
        if table and table.row_count == 0 and not state.get("broadened"):
            return "broaden_query"
        return "finish"

    # Execution failed
    if state.get("previous_identical") or len(state.get("attempts", [])) >= (
        1 + settings.SQL_MAX_RETRIES
    ):
        return "give_up"
    return "fix_sql"


def route_after_fix(state: SQLSubState) -> str:
    """Evaluate whether fix produced identical query or can proceed to static check."""
    if state.get("previous_identical"):
        return "give_up"
    return "static_check"


def build_sql_graph(deps: Dependencies | None = None) -> Any:
    """Compile the bounded self-correcting SQL sub-graph."""
    d = deps or Dependencies.default()

    builder = StateGraph(SQLSubState)

    # Bind dependency collaborators
    builder.add_node("load_schema", load_schema_node)
    builder.add_node(
        "generate_sql",
        partial(generate_sql_node, provider=d.provider),
    )
    builder.add_node(
        "static_check",
        partial(static_check_node, sql_tool=d.sql_tool),
    )
    builder.add_node(
        "execute_sql",
        partial(execute_sql_node, sql_tool=d.sql_tool),
    )
    builder.add_node(
        "fix_sql",
        partial(fix_sql_node, provider=d.provider),
    )
    builder.add_node(
        "broaden_query",
        partial(broaden_query_node, provider=d.provider),
    )
    builder.add_node("finish", finish_node)
    builder.add_node("give_up", give_up_node)

    # Wire edges
    builder.add_edge(START, "load_schema")
    builder.add_edge("load_schema", "generate_sql")
    builder.add_edge("generate_sql", "static_check")

    builder.add_conditional_edges(
        "static_check",
        route_after_static_check,
        ["execute_sql", "fix_sql", "give_up"],
    )

    builder.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        ["finish", "broaden_query", "fix_sql", "give_up"],
    )

    builder.add_conditional_edges(
        "fix_sql",
        route_after_fix,
        ["static_check", "give_up"],
    )

    builder.add_edge("broaden_query", "static_check")
    builder.add_edge("finish", END)
    builder.add_edge("give_up", END)

    return builder.compile()
