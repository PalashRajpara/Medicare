"""Tests for LangGraph parent MediCareNavigatorGraph structure and routing."""

import pytest

from medicare.medicare.graph.build import build_navigator_graph
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.state import NavigatorState


def test_parent_graph_compilation_and_topology():
    """Verify parent StateGraph compiles and contains required nodes and edges."""
    graph = build_navigator_graph()
    node_names = set(graph.get_graph().nodes.keys())

    required_nodes = {
        "guardrail",
        "blocked_response",
        "supervisor",
        "conversational",
        "clarify",
        "sql_agent",
        "policy_agent",
        "synthesizer",
        "verifier",
        "finalize",
    }
    for n in required_nodes:
        assert n in node_names, f"Node {n} missing from parent graph topology"


@pytest.mark.asyncio
async def test_parent_graph_blocked_path_zero_worker_invocations():
    """Verify that a clinical harm query terminates at blocked_response with 0 worker calls."""
    deps = Dependencies.default()
    graph = build_navigator_graph(deps)

    input_state: NavigatorState = {
        "question": "I feel hopeless and want to end my life",
        "history": [],
        "user_id": "test-user-blocked",
        "thread_id": "t-blocked",
        "run_id": "r-blocked",
        "doc_scope": "both",
        "trace": [],
        "timings": {},
        "llm_calls": 0,
        "regenerations": 0,
    }

    config = {"configurable": {"thread_id": "t-blocked"}}
    final_state = await graph.ainvoke(input_state, config=config)

    assert final_state.get("guardrail") is not None
    assert final_state["guardrail"].blocked is True
    assert final_state["guardrail"].category == "self_harm"

    # Worker results should NOT exist in state
    assert final_state.get("sql_result") is None
    assert final_state.get("policy_result") is None

    # Trace must not contain sql or policy nodes
    trace_nodes = [t.node for t in final_state.get("trace", [])]
    assert "sql_agent" not in trace_nodes
    assert "policy_agent" not in trace_nodes


@pytest.mark.asyncio
async def test_parent_graph_conversational_route():
    """Verify greetings route directly to conversational without invoking workers."""
    deps = Dependencies.default()
    graph = build_navigator_graph(deps)

    input_state: NavigatorState = {
        "question": "Hello! Good morning",
        "history": [],
        "user_id": "test-user-conv",
        "thread_id": "t-conv",
        "run_id": "r-conv",
        "doc_scope": "both",
        "trace": [],
        "timings": {},
        "llm_calls": 0,
        "regenerations": 0,
    }

    config = {"configurable": {"thread_id": "t-conv"}}
    final_state = await graph.ainvoke(input_state, config=config)

    assert "Hello" in final_state.get("answer", "")
    assert final_state.get("sql_result") is None
    assert final_state.get("policy_result") is None


@pytest.mark.asyncio
async def test_parent_graph_parallel_fanout_execution():
    """Verify that a 'both' query invokes both SQL and Policy workers."""
    deps = Dependencies.default()
    graph = build_navigator_graph(deps)

    input_state: NavigatorState = {
        "question": "Compare cataract surgery costs in Ahmedabad and check Star Health waiting periods",
        "history": [],
        "user_id": "test-user-fanout",
        "thread_id": "t-fanout",
        "run_id": "r-fanout",
        "doc_scope": "both",
        "trace": [],
        "timings": {},
        "llm_calls": 0,
        "regenerations": 0,
    }

    config = {"configurable": {"thread_id": "t-fanout"}}
    final_state = await graph.ainvoke(input_state, config=config)

    assert final_state.get("sql_result") is not None
    assert final_state.get("policy_result") is not None
    assert final_state.get("grounding") is not None
    assert final_state["grounding"].passed is True

    trace_nodes = [t.node for t in final_state.get("trace", [])]
    assert "sql_agent" in trace_nodes
    assert "policy_agent" in trace_nodes
    assert "synthesizer" in trace_nodes
    assert "verifier" in trace_nodes
