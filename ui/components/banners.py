"""Status and notice banners for MediCare UI."""

from collections.abc import Callable

import streamlit as st

from ui.config import get_app_config, get_messages_config


def render_sample_data_banner() -> None:
    """Render slim, persistent disclaimer banner indicating sample data."""
    cfg = get_app_config()
    messages = get_messages_config()
    ui_cfg = cfg.get("ui", {})
    banner_text = messages.get("disclaimer_banner") or ui_cfg.get("disclaimer_banner", "")
    st.markdown(
        f'<div class="sample-data-banner"><span>{banner_text}</span></div>',
        unsafe_allow_html=True,
    )


def render_backend_offline_banner(on_retry: Callable[[], None] | None = None) -> None:
    """Render full-width notification when backend service is unreachable."""
    cfg = get_app_config()
    messages = get_messages_config()
    ui_cfg = cfg.get("ui", {})
    offline_msg = messages.get("backend_offline_banner") or ui_cfg.get("backend_offline_banner", "")
    retry_label = messages.get("retry_button_label") or ui_cfg.get(
        "retry_button_label", "Retry Connection"
    )

    col_msg, col_btn = st.columns([5, 1])
    with col_msg:
        st.error(offline_msg, icon="🚨")
    with col_btn:
        if st.button(retry_label, key="retry_backend_btn", width="stretch"):
            if on_retry:
                on_retry()
            st.rerun()


def render_ai_offline_notice() -> None:
    """Render amber warning when AI model is offline and app is in fallback retrieval mode."""
    cfg = get_app_config()
    messages = get_messages_config()
    ui_cfg = cfg.get("ui", {})
    notice = messages.get("ai_offline_warning") or ui_cfg.get("ai_offline_warning", "")
    st.warning(notice, icon="⚠️")
