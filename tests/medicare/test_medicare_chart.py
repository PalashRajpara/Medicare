"""Tests for ChartSpec builder and Indian currency formatting."""

import json

from medicare.domain.models import TableResult
from medicare.medicare.chart import build_chart_spec
from medicare.medicare.graph.state import format_inr


def test_format_inr_helper():
    assert format_inr(125000) == "₹1,25,000"
    assert format_inr(1500000) == "₹15,00,000"
    assert format_inr(450) == "₹450"
    assert format_inr(0) == "₹0"
    assert format_inr(None) == "₹0"
    assert format_inr(-50000) == "-₹50,000"


def test_chart_spec_fewer_than_two_rows_skipped():
    """Verify that empty table or 1-row table skips chart generation."""
    assert build_chart_spec(None) is None

    empty_table = TableResult(columns=["hospital_name", "avg_cost_inr"], rows=[], row_count=0)
    assert build_chart_spec(empty_table) is None

    one_row = TableResult(
        columns=["hospital_name", "avg_cost_inr"],
        rows=[["Apollo", 150000]],
        row_count=1,
    )
    assert build_chart_spec(one_row) is None


def test_chart_spec_column_detection_and_serializability():
    """Verify multi-column detection and JSON serializability."""
    table = TableResult(
        columns=[
            "hospital_name",
            "city",
            "procedure_name",
            "min_cost_inr",
            "max_cost_inr",
            "avg_cost_inr",
            "avg_wait_days",
            "cashless_accepted",
        ],
        rows=[
            ["Apollo Hospital", "Ahmedabad", "Knee Replacement", 180000, 260000, 220000, 5, 1],
            ["Shalby Hospital", "Ahmedabad", "Knee Replacement", 160000, 240000, 195000, 3, 1],
            ["Sterling Hospital", "Ahmedabad", "Knee Replacement", 150000, 220000, 185000, 6, 0],
        ],
        row_count=3,
    )

    spec = build_chart_spec(table)
    assert spec is not None
    assert spec.x_axis == "hospital_name"
    assert spec.y_axis == "avg_cost_inr"
    assert spec.secondary_y_axis == "avg_wait_days"
    assert spec.color_by == "cashless_accepted"
    assert spec.error_min == "min_cost_inr"
    assert spec.error_max == "max_cost_inr"
    assert len(spec.data) == 3

    # Must be 100% JSON serializable
    json_str = spec.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["x_axis"] == "hospital_name"
    assert len(parsed["data"]) == 3
