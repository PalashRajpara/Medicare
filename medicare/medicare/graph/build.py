"""Parent graph builder compiling MediCareNavigatorGraph with LangGraph."""

import logging
from functools import partial
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from medicare.config import settings
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.nodes_parent import (
    blocked_response_node,
    clarify_node,
    conversational_node,
    finalize_node,
    guardrail_node,
    policy_worker_node,
    sql_worker_node,
    supervisor_node,
    synthesizer_node,
    verifier_node,
)
from medicare.medicare.graph.policy_subgraph import build_policy_graph
from medicare.medicare.graph.routing import (
    route_guardrail,
    route_supervisor,
    route_verifier,
)
from medicare.medicare.graph.sql_subgraph import build_sql_graph
from medicare.medicare.graph.state import NavigatorState

logger = logging.getLogger(__name__)


def build_navigator_graph(deps: Dependencies | None = None) -> Any:
    """Compile the full 5-node MediCare Multi-Agent LangGraph with parallel fan-out."""
    d = deps or Dependencies.default()

    # Compile the worker sub-graphs
    sql_sub = build_sql_graph(d)
    policy_sub = build_policy_graph(d)

    builder = StateGraph(NavigatorState)

    # 1. Add Parent Nodes
    builder.add_node("guardrail", guardrail_node)
    builder.add_node("blocked_response", blocked_response_node)
    builder.add_node(
        "supervisor",
        partial(supervisor_node, provider=d.provider, memory_store=d.memory_store),
    )
    builder.add_node(
        "conversational",
        partial(conversational_node, provider=d.provider),
    )
    builder.add_node("clarify", clarify_node)
    builder.add_node(
        "sql_agent",
        partial(sql_worker_node, sql_graph=sql_sub),
    )
    builder.add_node(
        "policy_agent",
        partial(policy_worker_node, policy_graph=policy_sub),
    )
    builder.add_node(
        "synthesizer",
        partial(synthesizer_node, provider=d.provider),
    )
    builder.add_node("verifier", verifier_node)
    builder.add_node(
        "finalize",
        partial(finalize_node, memory_store=d.memory_store),
    )

    # 2. Wire Edges
    builder.add_edge(START, "guardrail")

    builder.add_conditional_edges(
        "guardrail",
        route_guardrail,
        ["blocked_response", "supervisor"],
    )
    builder.add_edge("blocked_response", END)

    # Fan-out: supervisor to workers or early conversational/clarify
    builder.add_conditional_edges(
        "supervisor",
        route_supervisor,
        ["conversational", "clarify", "sql_agent", "policy_agent"],
    )

    builder.add_edge("conversational", END)
    builder.add_edge("clarify", END)

    # Workers converge on synthesizer
    builder.add_edge("sql_agent", "synthesizer")
    builder.add_edge("policy_agent", "synthesizer")

    # Synthesizer to Verifier
    builder.add_edge("synthesizer", "verifier")

    # Verifier conditional edge (repair regeneration or finalize)
    builder.add_conditional_edges(
        "verifier",
        route_verifier,
        ["synthesizer", "finalize"],
    )

    builder.add_edge("finalize", END)

    # Select checkpointer
    checkpointer = None
    if settings.LANGGRAPH_CHECKPOINTER == "memory":
        checkpointer = MemorySaver()
    elif settings.LANGGRAPH_CHECKPOINTER == "sqlite":
        try:
            import sqlite3

            from langgraph.checkpoint.sqlite import SqliteSaver

            conn = sqlite3.connect(settings.LANGGRAPH_CHECKPOINT_PATH, check_same_thread=False)
            checkpointer = SqliteSaver(conn)
        except Exception as e:
            logger.warning(f"Failed to initialize SqliteSaver ({e}). Using MemorySaver.")
            checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


_compiled_navigator_graph: Any = None


def get_compiled_navigator_graph(deps: Dependencies | None = None) -> Any:
    """Singleton accessor for compiled parent graph."""
    global _compiled_navigator_graph
    if _compiled_navigator_graph is None:
        _compiled_navigator_graph = build_navigator_graph(deps)
    return _compiled_navigator_graph
