"""Tests for MediCare query intent router and conversational entity tracking."""

from medicare.medicare.graph.routing import rules_route


def test_router_policy_only_classification():
    plan = rules_route("What are the waiting periods and claim rejection rules under Star Health?")
    assert plan.route in ("policy_only", "both")
    assert plan.entities.get("insurer") == "Star Health"


def test_router_data_only_classification():
    plan = rules_route("Compare procedural cost and wait times for hospitals in Ahmedabad")
    assert plan.route in ("data_only", "both")
    assert plan.entities.get("city") == "Ahmedabad"


def test_router_both_classification():
    plan = rules_route(
        "Compare knee replacement costs in Ahmedabad and check HDFC ERGO cashless waiting periods"
    )
    assert plan.route == "both"
    assert plan.entities.get("city") == "Ahmedabad"
    assert plan.entities.get("procedure") == "Knee Replacement"
    assert plan.entities.get("insurer") == "Hdfc Ergo"


def test_router_multi_turn_entity_inheritance():
    """Verify follow-up query inherits prior city/procedure from long-term memory preferences."""
    prior_prefs = {"city": "Ahmedabad", "procedure": "Knee Replacement"}
    plan = rules_route("And does Star Health accept cashless there?", prior_prefs=prior_prefs)
    assert plan.entities.get("city") == "Ahmedabad"
    assert plan.entities.get("procedure") == "Knee Replacement"
    assert plan.entities.get("insurer") == "Star Health"
