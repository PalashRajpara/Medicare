"""Shared sidebar component for all MediCare application pages."""

import streamlit as st

from ui.client import MediCareClient
from ui.config import get_app_config
from ui.state import (
    get_active_model,
    get_document_scope,
    get_show_trace,
    get_stream_tokens,
    get_thread_id,
    get_threads_cache,
    get_user_id,
    is_threads_cache_valid,
    reset_conversation,
    set_document_scope,
    set_messages,
    set_show_trace,
    set_stream_tokens,
    set_thread_id,
    set_threads_cache,
)


def render_sidebar(client: MediCareClient, nav_pages: list[st.Page] | None = None) -> None:
    """Render the standard multi-page sidebar."""
    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    app_name = cfg.get("app_name", "MediCare")

    with st.sidebar:
        # 1. App Title & Live Backend Status (At the very top of sidebar)
        badge_label = "Live"
        badge_class = "status-live"
        try:
            if not client.check_health():
                badge_label = "Offline"
                badge_class = "status-offline"
            else:
                m_status = client.get_medicare_status()
                if m_status.get("mode") == "mock":
                    badge_label = "Mock"
                    badge_class = "status-mock"
        except Exception:
            badge_label = "Offline"
            badge_class = "status-offline"

        st.markdown(
            f'<div class="sidebar-brand-header">'
            f'<span class="sidebar-brand-title">🏥 {app_name}</span>'
            f'<span class="sidebar-status-badge {badge_class}">'
            f'<span class="status-dot"></span> {badge_label}'
            f"</span></div>",
            unsafe_allow_html=True,
        )

        # 2. Navigation Links
        if nav_pages:
            for p in nav_pages:
                st.page_link(p)
            st.markdown("---")

        # 3. New Chat Button
        new_chat_btn = ui_cfg.get("new_chat_button", "➕ New Chat")
        if st.button(new_chat_btn, width="stretch", type="primary", key="sidebar_new_chat"):
            reset_conversation()
            st.rerun()

        st.markdown("---")

        # 4. Conversations (with search)
        st.markdown(f"**{ui_cfg.get('previous_chats_header', 'Conversations')}**")
        _render_conversations_list(client)

        st.markdown("---")

        # 4. Document Scope Selector
        scope_options = [
            ui_cfg.get("document_scope_both", "Both"),
            ui_cfg.get("document_scope_curated", "Curated"),
            ui_cfg.get("document_scope_mine", "Mine"),
        ]
        scope_map = {
            ui_cfg.get("document_scope_both", "Both"): "both",
            ui_cfg.get("document_scope_curated", "Curated"): "curated",
            ui_cfg.get("document_scope_mine", "Mine"): "mine",
        }
        inv_scope_map = {v: k for k, v in scope_map.items()}

        current_scope_val = get_document_scope()
        default_index = 0
        current_display = inv_scope_map.get(current_scope_val, scope_options[0])
        if current_display in scope_options:
            default_index = scope_options.index(current_display)

        doc_scope_title = ui_cfg.get("document_scope_label", "**Document Scope:**")
        st.caption(doc_scope_title)
        selected_scope_display = st.segmented_control(
            "Document Scope Filter",
            options=scope_options,
            default=scope_options[default_index],
            key="scope_segmented_control",
            label_visibility="collapsed",
        )
        if selected_scope_display and selected_scope_display in scope_map:
            set_document_scope(scope_map[selected_scope_display])

        # 5. User Documents Summary
        _render_documents_summary(client)

        st.markdown("---")

        # 6. Settings Expander
        settings_label = ui_cfg.get("settings_header", "Settings")
        with st.expander(settings_label, expanded=False):
            # Model badge
            current_model = get_active_model()
            st.caption(f"**Model**: `{current_model}`")

            # Stream tokens toggle
            stream_enabled = st.checkbox(
                ui_cfg.get("stream_tokens_label", "Stream Tokens (SSE)"),
                value=get_stream_tokens(),
                key="sidebar_stream_toggle",
            )
            set_stream_tokens(stream_enabled)

            # Show reasoning trace toggle
            trace_enabled = st.checkbox(
                ui_cfg.get("show_trace_label", "Show reasoning trace"),
                value=get_show_trace(),
                key="sidebar_trace_toggle",
            )
            set_show_trace(trace_enabled)

        st.markdown("---")

        # 7. Version & Footer Disclaimer (Version above Demo Notice)
        st.caption(ui_cfg.get("version_footer", "MediCare Multi-Agent Platform • v0.1.0"))
        st.caption(ui_cfg.get("disclaimer_banner", ""))


def _render_conversations_list(client: MediCareClient) -> None:
    """Render conversation search and thread buttons."""
    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    user_id = get_user_id()
    if not is_threads_cache_valid():
        try:
            threads = client.list_threads(user_id=user_id, limit=20)
            set_threads_cache(threads)
        except Exception:
            set_threads_cache([])

    threads = get_threads_cache()
    if not threads:
        st.caption(ui_cfg.get("no_previous_chats", ""))
        return

    search_query = st.text_input(
        ui_cfg.get("search_conversations_label", "Search conversations"),
        placeholder=ui_cfg.get("search_conversations_placeholder", "Filter chats..."),
        label_visibility="collapsed",
        key="conv_search_input",
    )

    filtered_threads = []
    for t in threads:
        if isinstance(t, dict):
            title = t.get("title") or "Conversation"
            th_id = t.get("thread_id", "")
        elif isinstance(t, str):
            title = f"Chat {t[:8]}"
            th_id = t
        else:
            continue

        if not search_query or search_query.lower() in title.lower():
            filtered_threads.append((th_id, title))

    active_th = get_thread_id()
    for th_id, title in filtered_threads[:8]:
        is_active = th_id == active_th
        btn_label = f"💬 {title}" if not is_active else f"👉 {title}"
        if st.button(btn_label, key=f"sidebar_th_{th_id}", width="stretch"):
            set_thread_id(th_id)
            try:
                hist_msgs = client.get_history(th_id)
                # Convert ChatMessage dicts if needed
                formatted_msgs = []
                for m in hist_msgs:
                    if isinstance(m, dict):
                        formatted_msgs.append(m)
                set_messages(formatted_msgs)
            except Exception:
                set_messages([])
            st.rerun()


@st.fragment
def _render_documents_summary(client: MediCareClient) -> None:
    """Render dynamic user documents summary badge."""
    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    user_id = get_user_id()
    try:
        docs = client.list_documents(user_id=user_id, scope="mine")
        ready_cnt = sum(1 for d in docs if d.get("status") == "ready")
        proc_cnt = sum(1 for d in docs if d.get("status") == "processing")
        if docs:
            st.caption(f"📁 **My Documents**: {ready_cnt} ready, {proc_cnt} processing")
        else:
            st.caption(ui_cfg.get("no_user_docs_badge", "📁 **My Documents**: 0 uploaded"))
    except Exception:
        st.caption(ui_cfg.get("docs_status_unavailable_badge", "📁 **My Documents**: unavailable"))
