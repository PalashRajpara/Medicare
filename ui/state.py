"""Streamlit session state management with typed accessors and cache control."""

import time
import uuid
from typing import Any

import streamlit as st

from ui.config import get_app_config

THREADS_CACHE_TTL = 30.0


def init_session_state() -> None:
    """Initialize necessary Streamlit session state keys with secure defaults."""
    cfg = get_app_config()
    default_model = cfg.get("default_model", "")

    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())

    if "active_agent" not in st.session_state:
        st.session_state.active_agent = "medicare-navigator"

    if "active_model" not in st.session_state:
        st.session_state.active_model = default_model

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "threads_cache" not in st.session_state:
        st.session_state.threads_cache = []

    if "threads_cache_time" not in st.session_state:
        st.session_state.threads_cache_time = 0.0

    if "stream_tokens" not in st.session_state:
        st.session_state.stream_tokens = True

    if "show_trace" not in st.session_state:
        st.session_state.show_trace = True

    if "doc_scope" not in st.session_state:
        st.session_state.doc_scope = "both"

    if "last_run_id" not in st.session_state:
        st.session_state.last_run_id = None

    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False

    if "cancel_requested" not in st.session_state:
        st.session_state.cancel_requested = False

    if "selected_sample_prompt" not in st.session_state:
        st.session_state.selected_sample_prompt = None


def get_user_id() -> str:
    """Return session user ID (never displayed in UI)."""
    return str(st.session_state.get("user_id", ""))


def get_thread_id() -> str:
    """Return active thread ID."""
    return str(st.session_state.get("thread_id", ""))


def set_thread_id(thread_id: str) -> None:
    """Set active thread ID."""
    st.session_state.thread_id = thread_id


def get_active_agent() -> str:
    """Return active agent identifier."""
    return str(st.session_state.get("active_agent", "medicare-navigator"))


def get_active_model() -> str:
    """Return selected foundational model identifier."""
    return str(st.session_state.get("active_model", ""))


def set_active_model(model: str) -> None:
    """Update selected foundational model."""
    st.session_state.active_model = model


def get_stream_tokens() -> bool:
    """Check if token streaming is enabled."""
    return bool(st.session_state.get("stream_tokens", True))


def set_stream_tokens(enabled: bool) -> None:
    """Enable or disable token streaming."""
    st.session_state.stream_tokens = enabled


def get_show_trace() -> bool:
    """Check if reasoning trace expander is enabled."""
    return bool(st.session_state.get("show_trace", True))


def set_show_trace(show: bool) -> None:
    """Toggle reasoning trace display."""
    st.session_state.show_trace = show


def get_document_scope() -> str:
    """Return active document scope filter (both, curated, mine)."""
    return str(st.session_state.get("doc_scope", "both"))


def set_document_scope(scope: str) -> None:
    """Set document scope filter."""
    st.session_state.doc_scope = scope


def get_messages() -> list[dict[str, Any]]:
    """Return current conversation messages."""
    return list(st.session_state.get("messages", []))


def set_messages(messages: list[dict[str, Any]]) -> None:
    """Set conversation messages."""
    st.session_state.messages = list(messages)


def append_message(message: dict[str, Any]) -> None:
    """Append a single message to conversation."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    st.session_state.messages.append(message)


def get_last_run_id() -> str | None:
    """Return run ID of last execution."""
    return st.session_state.get("last_run_id")


def set_last_run_id(run_id: str | None) -> None:
    """Set run ID of last execution."""
    st.session_state.last_run_id = run_id


def is_generating() -> bool:
    """Check if execution run is currently in progress."""
    return bool(st.session_state.get("is_generating", False))


def set_generating(running: bool) -> None:
    """Set execution generation state."""
    st.session_state.is_generating = running


def is_cancel_requested() -> bool:
    """Check if run cancellation was requested by user."""
    return bool(st.session_state.get("cancel_requested", False))


def request_cancel() -> None:
    """Request active stream execution cancellation."""
    st.session_state.cancel_requested = True


def clear_cancel_request() -> None:
    """Clear run cancellation flag."""
    st.session_state.cancel_requested = False


def get_selected_prompt() -> str | None:
    """Return user-selected sample prompt if clicked."""
    return st.session_state.get("selected_sample_prompt")


def set_selected_prompt(prompt: str | None) -> None:
    """Set sample prompt for input initialization."""
    st.session_state.selected_sample_prompt = prompt


def reset_conversation() -> None:
    """Start a new conversation session."""
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.last_run_id = None
    st.session_state.selected_sample_prompt = None
    st.session_state.is_generating = False
    st.session_state.cancel_requested = False
    invalidate_threads_cache()


def invalidate_threads_cache() -> None:
    """Force refresh of thread list on next render."""
    st.session_state.threads_cache_time = 0.0


def is_threads_cache_valid() -> bool:
    """Check if thread list cache has expired."""
    now = time.time()
    last = st.session_state.get("threads_cache_time", 0.0)
    return (now - last) < THREADS_CACHE_TTL


def get_threads_cache() -> list[dict[str, Any]]:
    """Return cached threads list."""
    return list(st.session_state.get("threads_cache", []))


def set_threads_cache(threads: list[dict[str, Any]]) -> None:
    """Update cached threads list and timestamp."""
    st.session_state.threads_cache = list(threads)
    st.session_state.threads_cache_time = time.time()
