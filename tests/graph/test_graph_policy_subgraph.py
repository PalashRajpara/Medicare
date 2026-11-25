"""Tests for corrective Policy RAG sub-graph."""

import pytest

from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.policy_subgraph import build_policy_graph
from medicare.medicare.graph.state import SupervisorPlan


def test_policy_subgraph_compiles():
    """Verify Policy RAG sub-graph compiles and contains expected nodes."""
    graph = build_policy_graph()
    node_names = set(graph.get_graph().nodes.keys())
    for n in [
        "plan_query",
        "retrieve",
        "grade_chunks",
        "rewrite_query",
        "build_citations",
        "no_evidence",
    ]:
        assert n in node_names


@pytest.mark.asyncio
async def test_policy_subgraph_successful_retrieval():
    """Verify that relevant policy queries extract citations with C1..Cn markers."""
    deps = Dependencies.default()
    graph = build_policy_graph(deps)

    plan = SupervisorPlan(
        route="policy_only",
        entities={"insurer": "Star Health"},
        rewritten_question="What is the waiting period for joint replacement under Star Health?",
    )

    res = await graph.ainvoke(
        {
            "question": "What is the waiting period for joint replacement?",
            "plan": plan,
            "doc_scope": "curated",
        }
    )

    citations = res.get("citations", [])
    assert len(citations) > 0
    assert res.get("no_evidence") is False
    assert citations[0].cite_id == "C1"
    assert citations[0].score >= 0.0
