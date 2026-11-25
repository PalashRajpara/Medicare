"""Plotly chart visualizer driven by ChartSpec."""

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PRIMARY_COLORS = ["#007A78", "#0284C7", "#F59E0B", "#10B981", "#6366F1", "#EC4899"]


def chart_spec_to_figure(chart_spec: dict[str, Any] | None) -> go.Figure | None:
    """Convert ChartSpec dictionary to styled Plotly figure.

    Returns None if fewer than 2 data points are available.
    """
    if not chart_spec or not isinstance(chart_spec, dict):
        return None

    data = chart_spec.get("data", [])
    if not data or len(data) < 2:
        return None

    df = pd.DataFrame(data)
    x_axis = chart_spec.get("x_axis")
    y_axis = chart_spec.get("y_axis")
    title = chart_spec.get("title", "")
    color_by = chart_spec.get("color_by")
    chart_type = chart_spec.get("chart_type", "grouped_bar")

    # If axis keys not found, fallback to first columns
    if not x_axis or x_axis not in df.columns:
        x_axis = df.columns[0]
    if not y_axis or y_axis not in df.columns:
        num_cols = df.select_dtypes(include=["number"]).columns
        y_axis = (
            num_cols[0]
            if len(num_cols) > 0
            else df.columns[1]
            if len(df.columns) > 1
            else df.columns[0]
        )

    color_col = color_by if (color_by and color_by in df.columns) else None

    if chart_type in ("grouped_bar", "bar"):
        fig = px.bar(
            df,
            x=x_axis,
            y=y_axis,
            color=color_col,
            barmode="group",
            title=title,
            color_discrete_sequence=PRIMARY_COLORS,
        )
    elif chart_type == "line":
        fig = px.line(
            df,
            x=x_axis,
            y=y_axis,
            color=color_col,
            title=title,
            color_discrete_sequence=PRIMARY_COLORS,
        )
    else:
        fig = px.bar(
            df,
            x=x_axis,
            y=y_axis,
            color=color_col,
            barmode="group",
            title=title,
            color_discrete_sequence=PRIMARY_COLORS,
        )

    fig.update_layout(
        template="plotly_white",
        margin=dict(l=30, r=20, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title=x_axis.replace("_", " ").title(),
        yaxis_title=y_axis.replace("_", " ").title(),
    )
    return fig


def render_results_chart(chart_spec: dict[str, Any] | None, key_prefix: str = "") -> None:
    """Render Plotly chart in Streamlit container."""
    fig = chart_spec_to_figure(chart_spec)
    if fig is None:
        return

    st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_chart")
