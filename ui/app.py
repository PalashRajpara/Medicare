"""MediCare Multi-Agent Platform Main Application Router."""

import contextlib
import os
from pathlib import Path

import streamlit as st

from ui.client import MediCareClient
from ui.components.sidebar import render_sidebar
from ui.config import get_app_config, get_messages_config
from ui.state import init_session_state

# 1. Configuration & Page Settings
cfg = get_app_config()
messages = get_messages_config()
ui_cfg = cfg.get("ui", {})
page_title = messages.get("page_title") or ui_cfg.get("page_title", "MediCare")
page_icon = messages.get("page_icon") or ui_cfg.get("page_icon", "🏥")

st.set_page_config(
    page_title=page_title,
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Inject Styles
styles_path = Path(__file__).resolve().parent / "styles.css"
if styles_path.exists():
    with contextlib.suppress(Exception):
        st.html(f"<style>{styles_path.read_text(encoding='utf-8')}</style>")

# 3. Session State Initialization
init_session_state()

# 4. Gateway Client Setup
backend_url = os.getenv("BACKEND_SERVICE_URL") or ui_cfg.get("backend_service_url", "")
secret_token = os.getenv("SERVICE_SECRET_KEY", None)
client = MediCareClient(base_url=backend_url, secret_token=secret_token)

# 5. Multi-page Navigation Router (hidden from default sidebar top injection)
nav_chat_label = messages.get("nav_chat_label") or ui_cfg.get("nav_chat_label", "Chat")
nav_documents_label = messages.get("nav_documents_label") or ui_cfg.get(
    "nav_documents_label", "My Documents"
)
nav_how_it_works_label = messages.get("nav_how_it_works_label") or ui_cfg.get(
    "nav_how_it_works_label", "How It Works"
)

nav_pages = [
    st.Page(
        "pages/chat.py",
        title=nav_chat_label,
        icon=":material/chat:",
        default=True,
    ),
    st.Page(
        "pages/documents.py",
        title=nav_documents_label,
        icon=":material/folder:",
    ),
    st.Page(
        "pages/how_it_works.py",
        title=nav_how_it_works_label,
        icon=":material/info:",
    ),
]

nav = st.navigation(nav_pages, position="hidden")

# 6. Shared Sidebar Across All Pages
render_sidebar(client, nav_pages)

nav.run()
