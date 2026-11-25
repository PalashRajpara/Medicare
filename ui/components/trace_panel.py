"""Execution reasoning audit trace expander with multi-agent diagnostic tabs."""

from typing import Any

import pandas as pd
import streamlit as st

from ui.components.results_chart import PRIMARY_COLORS
from ui.config import get_app_config


def render_trace_panel(medicare_meta: dict[str, Any] | None, show_trace: bool = True) -> None:
    """Render 'How I got this' expander with Plan, SQL, Policy, Grounding, and Timings tabs."""
    if not show_trace or not medicare_meta:
        return

    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    expander_title = ui_cfg.get("how_i_got_this_label", "🔍 How I got this")

    plan_data = medicare_meta.get("plan", {})
    sql_trace = medicare_meta.get("sql_trace", [])
    citations = medicare_meta.get("citations", [])
    grounding = medicare_meta.get("grounding", {})
    timings = medicare_meta.get("timings_ms", {})

    with st.expander(expander_title, expanded=False):
        tab_plan, tab_sql, tab_policy, tab_ground, tab_time = st.tabs(
            [
                ui_cfg.get("trace_tab_plan", "Plan"),
                ui_cfg.get("trace_tab_sql", "SQL"),
                ui_cfg.get("trace_tab_policy", "Policy Search"),
                ui_cfg.get("trace_tab_grounding", "Grounding"),
                ui_cfg.get("trace_tab_timings", "Timings"),
            ]
        )

        with tab_plan:
            route = plan_data.get("route") or medicare_meta.get("route", "both")
            confidence = plan_data.get("confidence", 1.0)
            rationale = plan_data.get("rationale") or "Autonomous route selection"
            entities = plan_data.get("entities", {})
            rewritten_q = plan_data.get("rewritten_question", "")

            st.markdown(f"**Route**: `{route}` (Confidence: `{confidence:.2f}`)")
            if rationale:
                st.markdown(f"**Rationale**: {rationale}")
            if rewritten_q:
                st.markdown(f"**Rewritten Query**: *{rewritten_q}*")
            if entities:
                ent_str = ", ".join(f"`{k}`: {v}" for k, v in entities.items() if v)
                if ent_str:
                    st.markdown(f"**Entities**: {ent_str}")

        with tab_sql:
            if not sql_trace:
                st.caption(ui_cfg.get("audit_no_sql_caption", ""))
            else:
                for att in sql_trace:
                    attempt_num = att.get("attempt", 1)
                    sql_str = att.get("sql", "")
                    err = att.get("error")
                    row_cnt = att.get("row_count")

                    st.markdown(f"**Attempt {attempt_num}** ({row_cnt} rows returned):")
                    if sql_str:
                        st.code(sql_str, language="sql")
                    if err:
                        st.warning(f"Error encountered: `{err}`")

        with tab_policy:
            if not citations:
                st.caption(ui_cfg.get("audit_no_policy_caption", ""))
            else:
                st.caption(f"Retrieved {len(citations)} policy clauses:")
                for idx, c in enumerate(citations):
                    src = c.get("source") or c.get("filename") or "Document"
                    sec = c.get("section", "General")
                    score = c.get("score", 0.0)
                    cite_id = c.get("cite_id") or f"C{idx + 1}"
                    txt = c.get("text", "")

                    st.markdown(f"**[{cite_id}] {src}** — *Section: {sec}* (Score: `{score:.2f}`)")
                    if txt:
                        st.markdown(f"> {txt[:250]}..." if len(txt) > 250 else f"> {txt}")

        with tab_ground:
            passed = grounding.get("passed", True)
            issues = grounding.get("issues", [])
            fallback_used = grounding.get("fallback_used", False)
            regenerated = grounding.get("regenerated", False)

            if passed:
                st.success(ui_cfg.get("audit_grounding_verified", "Grounding Verified"))
            else:
                st.warning(ui_cfg.get("audit_grounding_issues", "Grounding Issues Detected"))

            if issues:
                for issue in issues:
                    st.markdown(f"• `{issue}`")
            if regenerated:
                st.info(ui_cfg.get("audit_grounding_repaired", "Regenerated to repair grounding"))
            if fallback_used:
                st.warning(
                    ui_cfg.get("audit_grounding_fallback", "Deterministic verified fallback used")
                )

        with tab_time:
            if not timings:
                st.caption(ui_cfg.get("audit_no_timings_caption", ""))
            else:
                timing_records = [
                    {"Stage": k.replace("_", " ").title(), "Time (ms)": v}
                    for k, v in timings.items()
                    if isinstance(v, (int, float))
                ]
                if timing_records:
                    tdf = pd.DataFrame(timing_records)
                    st.bar_chart(
                        tdf,
                        x="Stage",
                        y="Time (ms)",
                        color=PRIMARY_COLORS[0],
                    )
                else:
                    st.caption(ui_cfg.get("audit_no_timings", ""))
