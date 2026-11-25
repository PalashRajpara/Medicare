"""Architecture explanation and live system diagnostics for MediCare multi-agent platform."""

import os

import streamlit as st

from ui.client import MediCareClient
from ui.config import get_app_config

# 1. Config & Client
cfg = get_app_config()
ui_cfg = cfg.get("ui", {})
backend_url = os.getenv("BACKEND_SERVICE_URL") or ui_cfg.get("backend_service_url", "")
secret_token = os.getenv("SERVICE_SECRET_KEY", None)
client = MediCareClient(base_url=backend_url, secret_token=secret_token)

# 2. Page Header
st.title(ui_cfg.get("how_it_works_title", "How It Works"))
intro_text = ui_cfg.get("how_it_works_intro", "")
if intro_text:
    st.caption(intro_text)


def _clean_title(val: str) -> str:
    """Strip any markdown heading hashes and whitespace."""
    return val.lstrip("#").strip()


# 3. Agent Responsibilities (Compact 3-Column Grid)
st.markdown(f"#### {ui_cfg.get('agent_roles_header', 'Autonomous Agent Roles')}")
col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown(f"**{_clean_title(ui_cfg.get('role_guardrail_title', '🛡️ Safety Guardrail'))}**")
        st.caption(ui_cfg.get("role_guardrail_desc", ""))

    with st.container(border=True):
        st.markdown(f"**{_clean_title(ui_cfg.get('role_policy_title', '📋 Policy RAG Agent'))}**")
        st.caption(ui_cfg.get("role_policy_desc", ""))

with col2:
    with st.container(border=True):
        st.markdown(
            f"**{_clean_title(ui_cfg.get('role_supervisor_title', '🧭 Supervisor Agent'))}**"
        )
        st.caption(ui_cfg.get("role_supervisor_desc", ""))

    with st.container(border=True):
        st.markdown(
            f"**{_clean_title(ui_cfg.get('role_writer_title', '✍️ Synthesizer & Writer'))}**"
        )
        st.caption(ui_cfg.get("role_writer_desc", ""))

with col3:
    with st.container(border=True):
        st.markdown(f"**{_clean_title(ui_cfg.get('role_sql_title', '📊 Hospital SQL Agent'))}**")
        st.caption(ui_cfg.get("role_sql_desc", ""))

    with st.container(border=True):
        st.markdown(
            f"**{_clean_title(ui_cfg.get('role_verifier_title', '🔒 Grounding Verifier'))}**"
        )
        st.caption(ui_cfg.get("role_verifier_desc", ""))

# 4. Live Backend Status & Telemetry (Unified Compact Bar)
st.markdown(f"#### {ui_cfg.get('system_diagnostics_header', 'Live System Diagnostics')}")
try:
    status = client.get_medicare_status()
    tables = status.get("tables", {})
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("AI Mode", status.get("mode", "Live").upper())
    with c2:
        st.metric("Policy Chunks (RAG)", status.get("policy_chunks", 0))
    with c3:
        st.metric("Procedures", tables.get("hospital_procedures", 0))
    with c4:
        st.metric("Hospitals", tables.get("hospitals", 0))
    with c5:
        st.metric("Insurers", tables.get("insurer_acceptance", 0))

    stack_text = ui_cfg.get(
        "diagnostics_stack_summary",
        "**Engine:** LangGraph • Chroma • Hybrid",
    ).format(
        langgraph=status.get("langgraph_version", "Active"),
        embedding=status.get("embedding_backend", "chroma_default"),
        retrieval=status.get("retrieval", "hybrid"),
        chroma=status.get("chroma", "chroma_db"),
    )
    st.caption(stack_text)
except Exception as e:
    st.warning(f"{ui_cfg.get('diagnostics_unavailable_label', 'Diagnostics unavailable')}: {e}")
