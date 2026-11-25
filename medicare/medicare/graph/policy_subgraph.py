"""Builder compiling the corrective Policy Agent RAG sub-graph."""

from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from medicare.config import settings
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.nodes_policy import (
    PolicySubState,
    build_citations_node,
    grade_chunks_node,
    no_evidence_node,
    plan_query_node,
    retrieve_node,
    rewrite_query_node,
)


def route_after_grade(state: PolicySubState) -> str:
    """Evaluate whether enough relevant chunks were retrieved or query needs rewriting."""
    relevant = state.get("relevant_chunks", [])
    if len(relevant) >= settings.RAG_MIN_RELEVANT:
        return "build_citations"

    # Not enough relevant chunks
    rewrites = state.get("rewrites_used", 0)
    if rewrites >= settings.RAG_MAX_REWRITES:
        return "no_evidence"

    return "rewrite_query"


def build_policy_graph(deps: Dependencies | None = None) -> Any:
    """Compile the corrective Policy RAG sub-graph."""
    d = deps or Dependencies.default()

    builder = StateGraph(PolicySubState)

    # Add nodes with injected dependencies
    builder.add_node("plan_query", plan_query_node)
    builder.add_node(
        "retrieve",
        partial(retrieve_node, retriever=d.retriever),
    )
    builder.add_node(
        "grade_chunks",
        partial(grade_chunks_node, provider=d.provider),
    )
    builder.add_node(
        "rewrite_query",
        partial(rewrite_query_node, provider=d.provider),
    )
    builder.add_node("build_citations", build_citations_node)
    builder.add_node("no_evidence", no_evidence_node)

    # Wire edges
    builder.add_edge(START, "plan_query")
    builder.add_edge("plan_query", "retrieve")
    builder.add_edge("retrieve", "grade_chunks")

    builder.add_conditional_edges(
        "grade_chunks",
        route_after_grade,
        ["build_citations", "rewrite_query", "no_evidence"],
    )

    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("build_citations", END)
    builder.add_edge("no_evidence", END)

    return builder.compile()
