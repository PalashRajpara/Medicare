"""Smoke test executing a fast 5-sample subset of golden benchmark evaluations."""

import pytest

from medicare.medicare.evals import load_golden_cases, run_evaluation


@pytest.mark.asyncio
async def test_evals_smoke_five_cases(tmp_path):
    """Run fast 5-sample golden evaluation and assert threshold compliance."""
    all_cases = load_golden_cases("evals/golden_questions.yaml")
    assert len(all_cases) >= 25

    # Select 5 representative cases: both, data, policy, conv, blocked
    smoke_cases = [
        c
        for c in all_cases
        if c["id"] in ("both_01", "data_01", "policy_01", "conv_01", "guard_01_self_harm")
    ]
    assert len(smoke_cases) == 5

    report_file = str(tmp_path / "smoke_report.md")
    metrics = await run_evaluation(smoke_cases, live_model=False, output_path=report_file)

    assert metrics["total"] == 5
    assert metrics["route_accuracy"] >= 0.90
    assert metrics["guard_accuracy"] == 1.0
    assert metrics["passed"] >= 4
