"""Unified assistant message renderer for both live streaming and conversation history."""

from collections.abc import Callable
from typing import Any

import streamlit as st

from ui.client import MediCareClient
from ui.components.citations import render_citations_row
from ui.components.feedback import render_message_actions
from ui.components.results_chart import render_results_chart
from ui.components.results_table import render_results_table
from ui.components.suggestions import render_followup_chips
from ui.components.trace_panel import render_trace_panel
from ui.config import get_app_config


def render_assistant_answer(
    message: dict[str, Any],
    client: MediCareClient,
    show_trace: bool = True,
    is_latest: bool = False,
    on_regenerate: Callable[[], None] | None = None,
    on_followup_select: Callable[[str], None] | None = None,
    key_prefix: str = "msg",
) -> None:
    """Render an assistant message consistently across live runs and historical loads."""
    content = message.get("content", "")
    metadata = message.get("response_metadata", {})
    medicare_meta = metadata.get("medicare", {})
    run_id = message.get("run_id") or metadata.get("run_id")

    guardrail = medicare_meta.get("guardrail", {})
    is_blocked = guardrail.get("blocked", False)
    category = guardrail.get("category", "")

    # 1. Safety Guardrail & Blocked Responses
    if is_blocked:
        cfg = get_app_config()
        ui_cfg = cfg.get("ui", {})
        with st.container(border=True):
            if category in ("self_harm", "emergency"):
                st.error(ui_cfg.get("safety_helpline_notice", "Notice"), icon="🆘")
                st.markdown(f"### {content}")
            else:
                st.warning(ui_cfg.get("policy_notice_label", "Notice"), icon="ℹ️")
                st.markdown(content)
        return

    # 2. Markdown Answer Body
    st.markdown(content)

    # 3. Table and Chart Tabs
    table_data = medicare_meta.get("table")
    chart_data = medicare_meta.get("chart")
    has_table = bool(table_data and table_data.get("columns") and table_data.get("rows"))
    has_chart = bool(chart_data and len(chart_data.get("data", [])) >= 2)

    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    tab_table_label = ui_cfg.get("tab_table_label", "Table")
    tab_chart_label = ui_cfg.get("tab_chart_label", "Chart")

    if has_table and has_chart:
        tab_t, tab_c = st.tabs([f"📊 {tab_table_label}", f"📈 {tab_chart_label}"])
        with tab_t:
            render_results_table(table_data, key_prefix=f"{key_prefix}_tab")
        with tab_c:
            render_results_chart(chart_data, key_prefix=f"{key_prefix}_tab")
    elif has_table:
        render_results_table(table_data, key_prefix=f"{key_prefix}_table")
    elif has_chart:
        render_results_chart(chart_data, key_prefix=f"{key_prefix}_chart")

    # 4. Sources Row (Citations Popover Chips)
    citations = medicare_meta.get("citations", [])
    if citations:
        render_citations_row(citations, key_prefix=f"{key_prefix}_sources")

    # 5. Reasoning Trace ("How I got this" Expander)
    if show_trace and medicare_meta:
        render_trace_panel(medicare_meta, show_trace=show_trace)

    # 6. Follow-up Suggestions
    followups = medicare_meta.get("followups", [])
    if followups and on_followup_select:
        render_followup_chips(
            followups,
            on_select=on_followup_select,
            key_prefix=f"{key_prefix}_followups",
        )

    # 7. Action Buttons (Thumbs up/down, Copy, Regenerate)
    render_message_actions(
        client=client,
        run_id=run_id,
        answer_text=content,
        on_regenerate=on_regenerate if is_latest else None,
        key_prefix=f"{key_prefix}_act",
    )
