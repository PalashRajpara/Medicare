"""Tests for Supervisor planner, rules routing, and entity canonicalization."""

import pytest

from medicare.medicare.graph.routing import canonicalize_entities, rules_route
from medicare.medicare.graph.state import SupervisorPlan
from medicare.medicare.prompts import call_json
from medicare.providers.mock_engine import ScriptedProvider


def test_rules_route_conversational():
    """Verify casual greetings without domain keywords classify as conversational."""
    plan = rules_route("Hello there! Good afternoon")
    assert plan.route == "conversational"
    assert plan.confidence == 1.0


def test_rules_route_data_only():
    """Verify procedural cost comparison queries classify as data_only with scoping needed."""
    plan = rules_route("Compare knee replacement cost in Ahmedabad")
    assert plan.route == "data_only"
    assert plan.needs_clarification is True
    assert plan.entities.get("procedure") == "Knee Replacement"
    assert plan.entities.get("city") == "Ahmedabad"


def test_rules_route_targeted_metric_no_scoping():
    """Verify queries with explicit ranking criteria proceed directly without scoping."""
    plan = rules_route("What is the lowest knee replacement cost in Ahmedabad?")
    assert plan.route == "data_only"
    assert plan.needs_clarification is False
    assert plan.entities.get("procedure") == "Knee Replacement"
    assert plan.entities.get("city") == "Ahmedabad"


def test_rules_route_full_table_no_scoping():
    """Verify explicit full table requests bypass progressive scoping."""
    plan = rules_route("Show full comparison table for knee replacement in Ahmedabad")
    assert plan.route == "data_only"
    assert plan.needs_clarification is False


def test_rules_route_policy_only():
    """Verify policy clause and pre-existing disease inquiries classify as policy_only."""
    plan = rules_route("What is the pre-existing disease waiting period under Star Health?")
    assert plan.route == "policy_only"
    assert plan.entities.get("insurer") == "Star Health"


def test_rules_route_both():
    """Verify queries combining hospital costs and cashless insurance rules classify as both."""
    plan = rules_route(
        "Compare cataract surgery costs across hospitals in Ahmedabad and check Star Health cashless acceptance"
    )
    assert plan.route == "both"
    assert plan.entities.get("city") == "Ahmedabad"
    assert plan.entities.get("procedure") == "Cataract Surgery"
    assert plan.entities.get("insurer") == "Star Health"


def test_canonicalize_entities_fuzzy_match():
    """Verify difflib maps misspelled entities to valid canonical database values."""
    raw = {"city": "ahmedbad", "procedure": "knee replacment", "insurer": "star health"}
    canon = canonicalize_entities(raw)
    assert canon["city"] == "Ahmedabad"
    assert canon["procedure"] == "Knee Replacement"
    assert canon["insurer"] == "Star Health"


@pytest.mark.asyncio
async def test_supervisor_call_json_automatic_repair():
    """Verify call_json automatically repairs malformed JSON on first failure."""
    provider = ScriptedProvider(
        responses=[
            "Here is the plan: {invalid json bad format",  # Malformed attempt 1
            '{"route": "data_only", "entities": {"city": "Mumbai"}, "rewritten_question": "hospitals in Mumbai", "confidence": 0.95, "rationale": "ok"}',  # Repaired attempt 2
        ]
    )

    plan = await call_json(SupervisorPlan, "Analyze query", provider, model="scripted-test")
    assert plan.route == "data_only"
    assert plan.entities["city"] == "Mumbai"
    assert plan.confidence == 0.95
