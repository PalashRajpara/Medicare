"""Formatted results table and CSV exporter using native st.dataframe."""

from typing import Any

import pandas as pd
import streamlit as st

from ui.config import get_app_config


def humanize_column_name(col: str) -> str:
    """Transform snake_case column identifier to user-friendly title."""
    parts = col.replace("_", " ").split()
    return " ".join(p.capitalize() for p in parts)


# Alias for backwards compatibility
humanize_header = humanize_column_name


def is_currency_column(col_name: str, hints: list[str] | None = None) -> bool:
    """Check if column name indicates currency amount based on hints."""
    if hints is None:
        hints = get_app_config().get("currency_column_hints", [])
    col_lower = col_name.lower()
    return any(h in col_lower for h in hints)


def is_boolean_column(col_name: str, hints: list[str] | None = None) -> bool:
    """Check if column name indicates boolean flag based on hints."""
    if hints is None:
        hints = get_app_config().get("boolean_column_hints", [])
    col_lower = col_name.lower()
    return any(h in col_lower for h in hints)


def format_table_dataframe(
    columns: list[str],
    rows: list[list[Any]],
    currency_symbol: str = "",
) -> pd.DataFrame:
    """Construct pandas DataFrame with humanized headers and converted types."""
    if not columns or not rows:
        return pd.DataFrame(columns=[humanize_column_name(c) for c in columns])

    raw_df = pd.DataFrame(rows, columns=columns)
    cfg = get_app_config()
    cur_hints = cfg.get("currency_column_hints", [])
    bool_hints = cfg.get("boolean_column_hints", [])

    formatted_cols = {}
    for col in raw_df.columns:
        human_col = humanize_column_name(col)
        if is_currency_column(col, cur_hints):
            # Keep as numeric so Streamlit column_config can format with currency symbol
            raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")
        elif is_boolean_column(col, bool_hints):
            raw_df[col] = raw_df[col].apply(
                lambda v: (
                    True
                    if v in (1, True, "1", "true", "True")
                    else False
                    if v in (0, False, "0", "false", "False")
                    else v
                )
            )
        formatted_cols[col] = human_col

    return raw_df.rename(columns=formatted_cols)


def build_column_config(columns: list[str], currency_symbol: str = "") -> dict[str, Any]:
    """Generate Streamlit column_config dictionary for number and currency formatting."""
    cfg = get_app_config()
    sym = currency_symbol or cfg.get("currency_symbol", "")
    cur_hints = cfg.get("currency_column_hints", [])
    bool_hints = cfg.get("boolean_column_hints", [])

    column_config: dict[str, Any] = {}
    for col in columns:
        human_col = humanize_column_name(col)
        if is_currency_column(col, cur_hints):
            column_config[human_col] = st.column_config.NumberColumn(
                human_col,
                format=f"{sym} %,d" if sym else "%,d",
                help=f"Amount in {sym}" if sym else human_col,
            )
        elif is_boolean_column(col, bool_hints):
            column_config[human_col] = st.column_config.CheckboxColumn(
                human_col,
                help=human_col,
            )
    return column_config


def render_results_table(table_data: dict[str, Any] | None, key_prefix: str = "") -> None:
    """Render formatted interactive table and download button."""
    if not table_data:
        return

    columns = table_data.get("columns", [])
    rows = table_data.get("rows", [])
    if not columns or not rows:
        return

    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    currency_symbol = cfg.get("currency_symbol", "")
    download_label = ui_cfg.get("download_csv_label", "Download CSV")

    df = format_table_dataframe(columns, rows, currency_symbol=currency_symbol)
    col_config = build_column_config(columns, currency_symbol=currency_symbol)

    st.dataframe(
        df,
        column_config=col_config,
        hide_index=True,
        width="stretch",
    )

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=download_label,
        data=csv_data,
        file_name="medicare_results.csv",
        mime="text/csv",
        key=f"{key_prefix}_download_csv",
    )
