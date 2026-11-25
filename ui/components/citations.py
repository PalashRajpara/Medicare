"""Citation marker parsing and popover components."""

import re
from typing import Any

import streamlit as st

from ui.config import get_app_config

CITATION_PATTERN = re.compile(r"\[(C\d+)\]")


def parse_citation_markers(text: str) -> list[str]:
    """Extract list of citation marker keys (e.g. ['C1', 'C2']) from markdown text."""
    if not text:
        return []
    return list(dict.fromkeys(CITATION_PATTERN.findall(text)))


def render_citation_popover(
    citation: dict[str, Any],
    label: str | None = None,
    key: str | None = None,
) -> None:
    """Render a single citation popover button displaying verified excerpt and metadata."""
    cite_id = citation.get("cite_id") or "C"
    source = citation.get("source") or citation.get("filename") or "Document"
    section = citation.get("section") or "General"
    page = citation.get("page")
    scope = citation.get("scope", "curated")
    score = citation.get("score")
    excerpt = citation.get("text") or ""

    button_label = label or f"[{cite_id}] {source}"
    scope_badge = "📁 My Document" if scope == "user" else "📚 Curated Policy"

    with st.popover(button_label, help=f"View source excerpt from {source}"):
        st.markdown(f"**Source**: `{source}`")
        st.markdown(f"**Scope**: {scope_badge}")
        if section and section != "General":
            st.markdown(f"**Section**: {section}")
        if page is not None and page > 0:
            st.markdown(f"**Page**: {page}")
        if score is not None and score > 0:
            st.markdown(f"**Relevance**: `{score:.2f}`")
        if excerpt:
            st.markdown("---")
            st.markdown(f"> *{excerpt}*")


def render_citations_row(citations: list[dict[str, Any]], key_prefix: str = "") -> None:
    """Render horizontal row of citation popovers under answer."""
    if not citations:
        return

    cfg = get_app_config()
    ui_cfg = cfg.get("ui", {})
    sources_label = ui_cfg.get("sources_row_label", "Sources")

    st.markdown(f"**{sources_label}:**")
    cols = st.columns(min(len(citations), 5))
    for idx, c in enumerate(citations):
        col_idx = idx % min(len(citations), 5)
        cite_id = c.get("cite_id") or f"C{idx + 1}"
        source = c.get("source") or c.get("filename") or "Document"
        short_source = source.split("/")[-1].split("\\")[-1]
        if len(short_source) > 20:
            short_source = short_source[:18] + "…"

        with cols[col_idx]:
            render_citation_popover(
                citation=c,
                label=f"[{cite_id}] {short_source}",
                key=f"{key_prefix}_cite_popover_{idx}_{cite_id}",
            )
