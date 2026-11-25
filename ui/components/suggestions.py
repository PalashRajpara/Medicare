"""Empty-state capability cards, suggestion chips, and follow-up chips."""

from collections.abc import Callable

import streamlit as st

from ui.config import get_app_config, get_messages_config


def render_empty_state(
    on_select: Callable[[str], None],
    suggestions: list[str] | None = None,
) -> None:
    """Render welcome banner, dynamic suggestion chips, and capability cards when chat is empty."""
    cfg = get_app_config()
    messages = get_messages_config()
    ui_cfg = cfg.get("ui", {})
    empty_cfg = cfg.get("empty_state", {})
    welcome_title = empty_cfg.get("welcome_title") or ""
    welcome_subtitle = (
        empty_cfg.get("welcome_subtitle")
        or cfg.get("app_caption")
        or messages.get("welcome_subtitle")
        or messages.get("app_tagline", "")
    )

    if welcome_title:
        st.markdown(f"### {welcome_title}")
    if welcome_subtitle:
        st.caption(welcome_subtitle)
    st.write("")

    # Dynamic suggestion chips from backend (or fallback sample questions)
    chip_options = suggestions or cfg.get("sample_questions", [])
    if chip_options:
        queries_header = ui_cfg.get("suggested_queries_header") or messages.get(
            "suggested_queries_header", ""
        )
        if queries_header:
            st.caption(queries_header)
        # Display up to 3 chips horizontally
        chips_to_show = chip_options[:3]
        cols = st.columns(len(chips_to_show))
        chip_help = messages.get("chip_help_text")
        for idx, chip_text in enumerate(chips_to_show):
            with cols[idx]:
                if st.button(
                    f"💡 {chip_text}",
                    key=f"empty_chip_{idx}",
                    width="stretch",
                    help=chip_help,
                ):
                    on_select(chip_text)

    cards = empty_cfg.get("cards", [])
    explore_label = ui_cfg.get("explore_button_label") or messages.get("explore_button_label", "")
    if cards:
        card_cols = st.columns(len(cards))
        for idx, card in enumerate(cards):
            title = card.get("title", "")
            icon = card.get("icon", "🏥")
            desc = card.get("description", "")
            prompt = card.get("prompt", "")

            with card_cols[idx], st.container(border=True):
                st.markdown(f"**{icon} {title}**")
                st.caption(desc)
                if st.button(explore_label, key=f"card_btn_{idx}", width="stretch"):
                    on_select(prompt)


def render_followup_chips(
    followups: list[str],
    on_select: Callable[[str], None],
    key_prefix: str = "",
) -> None:
    """Render dynamic follow-up suggestion chips returned by backend."""
    if not followups:
        return

    cfg = get_app_config()
    messages = get_messages_config()
    ui_cfg = cfg.get("ui", {})
    followups_header = ui_cfg.get("suggested_followups_header") or messages.get(
        "suggested_followups_header", ""
    )
    if followups_header:
        st.markdown(followups_header)
    cols = st.columns(min(len(followups), 3))
    for idx, f_text in enumerate(followups[:3]):
        with cols[idx % min(len(followups), 3)]:
            if st.button(f"👉 {f_text}", key=f"{key_prefix}_fup_{idx}", width="stretch"):
                on_select(f_text)
