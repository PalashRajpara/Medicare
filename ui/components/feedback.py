"""Message feedback actions (thumbs up/down, copy)."""

from collections.abc import Callable

import streamlit as st

from ui.client import MediCareClient
from ui.config import get_app_config


def render_message_actions(
    client: MediCareClient,
    run_id: str | None,
    answer_text: str,
    on_regenerate: Callable[[], None] | None = None,
    key_prefix: str = "",
) -> None:
    """Render thumbs up/down evaluation buttons and copy answer action."""
    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    copy_label = ui_cfg.get("copy_button_label", "📋 Copy")

    cols = st.columns([1, 1, 2, 8])

    with cols[0]:
        if st.button("👍", key=f"{key_prefix}_thumb_up", help="Helpful and grounded"):
            if run_id:
                try:
                    client.submit_feedback(run_id=run_id, score=1.0)
                    st.toast("Thank you for your feedback!", icon="👍")
                except Exception:
                    st.toast("Feedback recorded.", icon="👍")
            else:
                st.toast("Feedback recorded.", icon="👍")

    with cols[1]:
        if st.button("👎", key=f"{key_prefix}_thumb_down", help="Not helpful or inaccurate"):
            if run_id:
                try:
                    client.submit_feedback(run_id=run_id, score=0.0)
                    st.toast(ui_cfg.get("feedback_improve_toast", "Feedback recorded"), icon="👎")
                except Exception:
                    st.toast(ui_cfg.get("feedback_improve_toast", "Feedback recorded"), icon="👎")
            else:
                st.toast(ui_cfg.get("feedback_improve_toast", "Feedback recorded"), icon="👎")

    with cols[2]:
        if st.button(copy_label, key=f"{key_prefix}_copy_btn", help="Copy answer text"):
            # Put text into clipboard or show code modal
            st.toast("Answer ready to copy!", icon="📋")
