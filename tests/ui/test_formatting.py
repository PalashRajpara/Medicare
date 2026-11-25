"""Unit tests for UI pure formatting functions, citations parsing, and chart conversions."""

import plotly.graph_objects as go

from ui.components.citations import parse_citation_markers
from ui.components.results_chart import chart_spec_to_figure
from ui.components.results_table import (
    build_column_config,
    format_table_dataframe,
    humanize_column_name,
    humanize_header,
    is_boolean_column,
    is_currency_column,
)


def test_parse_citation_markers():
    """Verify regex citation marker extraction from markdown."""
    text = "Under the Star Health policy [C1], cataract surgery requires a waiting period [C2]. Check clause [C1] again."
    markers = parse_citation_markers(text)
    assert markers == ["C1", "C2"]

    assert parse_citation_markers("") == []
    assert parse_citation_markers("No citations here.") == []
    assert parse_citation_markers("[C12] [C3] [C99]") == ["C12", "C3", "C99"]


def test_humanize_column_name():
    """Verify snake_case to title case conversion."""
    assert humanize_column_name("hospital_name") == "Hospital Name"
    assert humanize_column_name("avg_cost_inr") == "Avg Cost Inr"
    assert humanize_column_name("cashless_accepted") == "Cashless Accepted"
    assert humanize_header("book_id") == "Book Id"
    assert humanize_header("author_full_name") == "Author Full Name"


def test_is_currency_column():
    """Verify currency column identification via configured hints."""
    hints = ["cost", "rent", "fee", "price", "amount", "inr"]
    assert is_currency_column("avg_cost_inr", hints) is True
    assert is_currency_column("room_rent", hints) is True
    assert is_currency_column("consultation_fee", hints) is True
    assert is_currency_column("hospital_name", hints) is False
    assert is_currency_column("city", hints) is False


def test_is_boolean_column():
    """Verify boolean column identification via configured hints."""
    hints = ["cashless", "accredited", "accepted", "network", "active"]
    assert is_boolean_column("cashless_accepted", hints) is True
    assert is_boolean_column("nabh_accredited", hints) is True
    assert is_boolean_column("hospital_name", hints) is False


def test_format_table_dataframe():
    """Verify DataFrame construction and humanized column renaming."""
    cols = ["hospital_name", "avg_cost_inr", "cashless_accepted"]
    rows = [
        ["General Hospital", 45000, 1],
        ["City Clinic", 32000, 0],
    ]
    df = format_table_dataframe(cols, rows, currency_symbol="₹")
    assert list(df.columns) == ["Hospital Name", "Avg Cost Inr", "Cashless Accepted"]
    assert len(df) == 2
    assert df["Cashless Accepted"].tolist() == [True, False]


def test_format_table_dataframe_deduplication():
    """Verify duplicate rows are deduplicated cleanly."""
    cols = ["hospital_name", "avg_cost_inr", "avg_wait_days"]
    rows = [
        ["Sterling Hospital Gurukul", 170000, 5],
        ["Sterling Hospital Gurukul", 170000, 5],
        ["Sterling Hospital Gurukul", 170000, 5],
        ["Epic Hospital Empire City", 174000, 3],
        ["Epic Hospital Empire City", 174000, 3],
    ]
    df = format_table_dataframe(cols, rows, currency_symbol="₹")
    assert len(df) == 2
    assert list(df["Hospital Name"]) == ["Sterling Hospital Gurukul", "Epic Hospital Empire City"]


def test_build_column_config():
    """Verify Streamlit column config generation."""
    cols = ["hospital_name", "avg_cost_inr", "cashless_accepted"]
    cfg = build_column_config(cols, currency_symbol="₹")
    assert "Avg Cost Inr" in cfg
    assert "Cashless Accepted" in cfg
    assert "Hospital Name" not in cfg


def test_chart_spec_to_figure_minimum_rows():
    """Verify chart spec requires at least 2 rows to produce a figure."""
    spec_empty = {"data": []}
    assert chart_spec_to_figure(spec_empty) is None

    spec_single = {
        "title": "Single Row",
        "x_axis": "hospital",
        "y_axis": "cost",
        "data": [{"hospital": "Hospital A", "cost": 1000}],
    }
    assert chart_spec_to_figure(spec_single) is None

    spec_valid = {
        "title": "Cost Comparison",
        "x_axis": "hospital",
        "y_axis": "cost",
        "chart_type": "grouped_bar",
        "data": [
            {"hospital": "Hospital A", "cost": 1000},
            {"hospital": "Hospital B", "cost": 2000},
        ],
    }
    fig = chart_spec_to_figure(spec_valid)
    assert fig is not None
    assert isinstance(fig, go.Figure)
