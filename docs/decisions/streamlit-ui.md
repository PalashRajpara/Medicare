# Decision Record: Streamlit UI Production Rebuild

**Date:** 2026-11-23  
**Status:** Approved & Implemented  
**Context:** Rebuilding the Streamlit UI into a standard, production-quality interface with modern Streamlit 1.67+ primitives (`st.navigation`, `st.fragment`, `st.status`, `st.popover`, `st.segmented_control`, `st.dataframe(column_config=...)`), zero hardcoding, strict HTTP separation from backend, and complete removal of premature voice/audio prototype code.

---

## 1. Architectural Decisions

### 1.1 Multi-Page Navigation via `st.navigation`
- **Previous state:** Monolithic single-page script (`ui/app.py`) with all views crammed into an expander or sidebar drawers.
- **Decision:** Adopt modern Streamlit multi-page routing via `st.navigation` with three distinct pages:
  - `ui/pages/chat.py` (Default): Interactive conversational UI with empty-state capability cards, suggestion chips, live execution stepper, token streaming, table/chart tabs, citation popovers, reasoning trace expander, and feedback actions.
  - `ui/pages/documents.py`: Document ingestion interface with file drag-and-drop, metadata inputs (insurer, doc type), live polling status table with deletion controls, and curated reference document inspection.
  - `ui/pages/how_it_works.py`: Plain-language explanation of autonomous agent roles, Mermaid state graph visualizers (`graph_parent.mmd`, `graph_sql.mmd`, `graph_policy.mmd`), and live system telemetry metrics.
- **Entry point (`ui/app.py`):** Configures layout, injects clean CSS, initializes session state, renders the shared sidebar across all pages, and executes `st.navigation.run()`.

### 1.2 Voice & Audio Scope Exclusion
- **Decision:** Voice input/output is explicitly excluded from this release.
- **Actions taken:**
  - Removed `ui/components/audio.py` and deleted all speech/audio imports from the UI.
  - Added feature flag `features.voice: false` in `config/app.yaml`.
  - Added a one-line roadmap entry in `README.md`.
  - Automated audit test `tests/ui/test_no_voice_audit.py` enforces zero audio widgets or imports across `ui/`.

### 1.3 Zero Hardcoding & Configuration Injection
- **Rule:** UI contains zero hardcoded domain data (cities, hospitals, insurers, procedures, tariffs) and zero hardcoded user-facing strings.
- **Actions taken:**
  - Added public `GET /app/config` endpoint in `medicare/api/routes/info.py` returning safe UI labels and features from `config/app.yaml`.
  - All titles, badges, empty-state cards, buttons, and captions are retrieved from `config/app.yaml` through `ui_cfg.get(...)`.
  - Automated audit scanner (`tests/medicare/test_no_hardcoding.py` and `tests/ui/test_ui_no_hardcoding.py`) enforces 0 unallowlisted hardcoded elements.

### 1.4 Single Unified Message Rendering Path
- **Previous state:** Inconsistent visual formatting between live streamed tokens and historical messages loaded from `/history`.
- **Decision:** Implemented `ui/components/answer.py::render_assistant_answer` as the single canonical render function. Both live executions (upon completion) and historical thread messages use the exact same code path, guaranteeing 100% visual identity.

### 1.5 Native Streamlit Primitives over Heavy HTML
- **Table & Formatting:** Native `st.dataframe` with `column_config` (`NumberColumn` with currency formatting and `CheckboxColumn` for booleans) plus a **Download CSV** button.
- **Charts:** Plotly figures converted from `ChartSpec` adhering to the healthcare color palette; automatically hidden when data has fewer than 2 rows.
- **Citations:** Clickable `st.popover` chips showing source document, scope badge (`Curated Policy` vs `My Document`), section, page, score, and verbatim excerpt.
- **Live Stepper:** Native `st.status` displaying execution stages (Guardrail, Supervisor, SQL Agent, Policy RAG Agent, Writer, Verifier) with icon + text and retry/rewrite indicators, auto-collapsing upon answer generation.
- **Live Polling:** Isolated with `@st.fragment` so background document indexing or status refreshes do not trigger full page reruns.

### 1.6 Strict HTTP-Only Architecture
- `ui/` communicates with the backend exclusively over HTTP via `ui/client.py`.
- No direct imports from `medicare/` are permitted in `ui/`, verified by AST architectural layering checks (`scripts/verify_layout.py`).

---

## 2. Component Layout & Directory Structure

```
ui/
├── __init__.py
├── app.py                 # Router, page config, shared sidebar
├── client.py              # HTTP & SSE client with typed calls, timeout, and cancellation
├── config.py              # App config loader independent of backend package
├── state.py               # Typed Session State accessors and cache invalidation
├── styles.css             # Lightweight CSS for cards, chips, and disclaimer banners
├── pages/
│   ├── chat.py            # Primary chat page with streaming and stepper
│   ├── documents.py       # Document upload, polling, and deletion
│   └── how_it_works.py    # Architecture, Mermaid diagrams, and telemetry
└── components/
    ├── answer.py          # Unified assistant message renderer
    ├── banners.py         # Sample data banner and backend offline notifications
    ├── citations.py       # [C1] marker parsing and popover chips
    ├── feedback.py        # Thumbs up/down evaluation and message actions
    ├── results_chart.py   # Plotly chart renderer from ChartSpec
    ├── results_table.py   # Humanized st.dataframe with column_config and CSV export
    ├── sidebar.py         # Shared sidebar: search, scope selector, settings, status
    ├── stepper.py         # Live multi-agent execution status stepper
    ├── suggestions.py     # Empty state cards, suggestion chips, and follow-ups
    └── trace_panel.py     # "How I got this" expander with Plan, SQL, Policy, Grounding, Timings
```

---

## 3. Verification & Compliance
- **All 153 tests passing** in `pytest`.
- **Ruff check & format**: 100% clean across all 191 repository files.
- **Layout verification**: Passed with 0 violations.
- **Hardcode audit**: 0 unallowlisted findings in `ui/` or `medicare/`.
