"""Unit tests for progressive scoping, candidate hospital discovery, and follow-up chips."""

import pytest

from medicare.domain.models import TableResult
from medicare.medicare.graph.routing import (
    generate_scoping_followups,
    is_underspecified_comparison,
)
from medicare.medicare.graph.state import SQLAgentResult, SupervisorPlan
from medicare.medicare.graph.verify import build_deterministic_fallback, build_scoping_response


def test_is_underspecified_comparison_broad_query():
    """Verify broad comparative query with multiple candidates is flagged as underspecified."""
    q = "Compare Total Hip Replacement costs in Ahmedabad"
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    assert is_underspecified_comparison(q, entities, candidate_count=3) is True


def test_is_underspecified_comparison_single_hospital_bypasses():
    """Verify single candidate hospital is not treated as comparative scoping."""
    q = "Compare Total Hip Replacement costs in Ahmedabad"
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    assert is_underspecified_comparison(q, entities, candidate_count=1) is False


def test_is_underspecified_comparison_insurer_provided_bypasses():
    """Verify query with insurer provided bypasses scoping clarification."""
    q = "Compare Total Hip Replacement costs in Ahmedabad under Star Health"
    entities = {
        "city": "Ahmedabad",
        "procedure": "Total Hip Replacement",
        "insurer": "Star Health",
    }
    assert is_underspecified_comparison(q, entities, candidate_count=3) is False


def test_is_underspecified_comparison_specific_metric_bypasses():
    """Verify query specifying lowest cost or shortest wait bypasses scoping clarification."""
    q1 = "Lowest package cost for Hip Replacement in Ahmedabad"
    q2 = "Shortest wait time for Hip Replacement in Ahmedabad"
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    assert is_underspecified_comparison(q1, entities, candidate_count=3) is False
    assert is_underspecified_comparison(q2, entities, candidate_count=3) is False


def test_is_underspecified_comparison_full_table_bypasses():
    """Verify explicit full table request bypasses scoping clarification."""
    q = "Show full comparison table for Hip Replacement in Ahmedabad"
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    assert is_underspecified_comparison(q, entities, candidate_count=3) is False


def test_generate_scoping_followups_returns_four_actionable_chips():
    """Verify 4 distinct interactive follow-up chips are generated with city name."""
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    chips = generate_scoping_followups(entities)
    assert len(chips) == 4
    assert any("Lowest" in c for c in chips)
    assert any("Shortest" in c for c in chips)
    assert any("cashless" in c.lower() for c in chips)
    assert any("table" in c.lower() for c in chips)


def test_build_scoping_response_contains_hospitals_and_questions():
    """Verify build_scoping_response structures candidate hospitals and counter-questions."""
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    hospitals = [
        "Shalby Multi-Specialty Hospital - SG Highway",
        "Epic Hospital - Empire City",
        "Marengo CIMS Hospital",
    ]
    resp = build_scoping_response(
        entities=entities,
        hospitals=hospitals,
        min_cost=203000,
        max_cost=212000,
    )
    assert "Shalby" in resp
    assert "Epic" in resp
    assert "Marengo" in resp
    assert "health insurance" in resp.lower()
    assert "priority" in resp.lower()


def test_build_deterministic_fallback_scoping_vs_full_table():
    """Verify build_deterministic_fallback switches between scoping and full table based on query intent."""
    entities = {"city": "Ahmedabad", "procedure": "Total Hip Replacement"}
    table = TableResult(
        columns=["hospital_name", "avg_cost_inr", "avg_wait_days"],
        rows=[
            ["Shalby Multi-Specialty", 203000, 6],
            ["Epic Hospital", 206000, 5],
            ["Marengo CIMS", 212000, 6],
        ],
        row_count=3,
    )
    sql_res = SQLAgentResult(table=table, success=True)

    # 1. Underspecified broad query -> scoping response
    plan_broad = SupervisorPlan(
        route="data_only",
        entities=entities,
        rewritten_question="Compare Total Hip Replacement costs in Ahmedabad",
    )
    resp_broad = build_deterministic_fallback(plan_broad, sql_res, None)
    assert "health insurance" in resp_broad.lower()
    assert "| Shalby Multi-Specialty |" not in resp_broad

    # 2. Explicit full table request -> rendered comparison table
    plan_table = SupervisorPlan(
        route="data_only",
        entities=entities,
        rewritten_question="Show full comparison table for Hip Replacement in Ahmedabad",
    )
    resp_table = build_deterministic_fallback(plan_table, sql_res, None)
    assert "| Shalby Multi-Specialty |" in resp_table
    assert "| Hospital Name |" in resp_table


def test_rules_route_fuzzy_typo_city_resolution():
    """Verify misspelled city in query (e.g. 'ahmdabad') resolves to canonical 'Ahmedabad'."""
    from medicare.medicare.graph.routing import rules_route

    plan = rules_route("how much hospitals in ahmdabad")
    assert plan.entities.get("city") == "Ahmedabad"
    assert "Ahmedabad" in plan.rewritten_question
    assert plan.route == "data_only"


def test_build_deterministic_fallback_hospital_count_no_jargon():
    """Verify hospital count query produces professional guidance without database/evidence pack jargon."""
    entities = {"city": "Ahmedabad"}
    table = TableResult(
        columns=["hospital_count"],
        rows=[[10]],
        row_count=1,
    )
    sql_res = SQLAgentResult(table=table, success=True)
    plan = SupervisorPlan(
        route="data_only",
        entities=entities,
        rewritten_question="how much hospitals in Ahmedabad",
    )

    resp = build_deterministic_fallback(plan, sql_res, None)
    assert "10 accredited hospitals" in resp
    assert "Ahmedabad" in resp
    # Strict anti-jargon verification
    assert "evidence pack" not in resp.lower()
    assert "database row" not in resp.lower()
    assert "exact numbers aren't visible" not in resp.lower()
    assert "pull the exact numbers" not in resp.lower()


@pytest.mark.asyncio
async def test_end_to_end_typo_hospital_count_no_jargon():
    """Verify end-to-end execution of misspelled count query yields 10 hospitals without database jargon."""
    from medicare.medicare.graph.build import build_navigator_graph
    from medicare.medicare.graph.deps import Dependencies

    deps = Dependencies.default()
    graph = build_navigator_graph(deps)
    question = "how much hospitals in ahmdabad"
    initial_state = {
        "question": question,
        "history": [],
        "user_id": "test_typo_count_user",
        "doc_scope": "both",
    }
    result = await graph.ainvoke(
        initial_state, config={"configurable": {"thread_id": "thread_typo_count"}}
    )
    answer = result.get("answer", "")
    assert "10 accredited hospitals" in answer
    assert "Ahmedabad" in answer
    assert "evidence pack" not in answer.lower()
    assert "database row" not in answer.lower()
    assert "exact numbers aren't visible" not in answer.lower()
