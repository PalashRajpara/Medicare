"""Tests for GroundingVerifier and deterministic fallback synthesizer."""

from medicare.medicare.graph.state import (
    Citation,
    PolicyAgentResult,
    SQLAgentResult,
    SupervisorPlan,
    TableResult,
)
from medicare.medicare.graph.verify import build_deterministic_fallback, verify_grounding


def test_verify_grounding_valid_figures_pass():
    """Verify that numbers present in the SQL table pass grounding checks."""
    table = TableResult(
        columns=["hospital_name", "avg_cost_inr", "avg_wait_days"],
        rows=[
            ["Apple Hospital", 36000, 1],
            ["Ruby General Hospital", 36000, 1],
        ],
        row_count=2,
    )
    citations = [
        Citation(
            source="Star_Policy.md",
            section="Waiting Period",
            text="Waiting period for cataract surgery is 24 months.",
            score=0.9,
            cite_id="C1",
        )
    ]

    answer = (
        "Cataract surgery costs ₹36,000 with typical wait of 1 day at Apple Hospital. "
        "The waiting period under Star Health is 24 months [C1]."
    )

    report = verify_grounding(answer=answer, table=table, citations=citations)
    assert report.passed is True
    assert len(report.issues) == 0


def test_verify_grounding_ungrounded_numeric_claim_detected():
    """Verify that hallucinated figures not in table or citations are flagged."""
    table = TableResult(
        columns=["hospital_name", "avg_cost_inr"],
        rows=[["Apple Hospital", 36000]],
        row_count=1,
    )

    answer = "The procedure at Apple Hospital costs ₹99,999 which is very expensive."
    report = verify_grounding(answer=answer, table=table, citations=[])

    assert report.passed is False
    assert any("99,999" in iss or "99999" in iss for iss in report.issues)


def test_deterministic_fallback_passes_grounding_100_percent():
    """Verify that build_deterministic_fallback always passes grounding verification."""
    table = TableResult(
        columns=["hospital_name", "avg_cost_inr", "avg_wait_days"],
        rows=[
            ["Sterling Hospital", 125000, 3],
            ["Shalby Hospital", 110000, 2],
        ],
        row_count=2,
    )
    citations = [
        Citation(
            source="HDFC_Ergo_Policy.md",
            section="Pre-Existing Diseases",
            text="Pre-existing conditions covered after 36 months.",
            score=0.88,
            cite_id="C1",
        )
    ]

    plan = SupervisorPlan(
        route="both",
        entities={"city": "Ahmedabad", "procedure": "Knee Replacement"},
    )
    sql_res = SQLAgentResult(table=table, success=True)
    pol_res = PolicyAgentResult(citations=citations)

    fallback_text = build_deterministic_fallback(
        plan=plan, sql_result=sql_res, policy_result=pol_res
    )

    assert "Sterling Hospital" in fallback_text
    assert "₹1,25,000" in fallback_text or "125000" in fallback_text

    # Run verifier on the generated fallback text
    report = verify_grounding(answer=fallback_text, table=table, citations=citations)
    assert report.passed is True
