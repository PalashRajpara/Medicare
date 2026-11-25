# Decision Record: Repository Reorganization & Layout Standardization

**Date:** 2026-11-23  
**Status:** Approved & In-Progress  
**Context:** Standardizing repository structure, establishing clean architectural layering, moving runtime state to `var/`, reorganizing tests and documentation, and eliminating dead/unreachable prototype code.

---

## 1. Dead Code & Module Reachability Analysis

As part of the architecture cleanup and standardization, every module in `medicare/` was analyzed for reachability from production entry points (`medicare.api.app:create_app`, `ui/app.py`, `medicare.medicare.setup`, `medicare.medicare.evals`, `scripts/`).

| Module | Reachable from Prod? | Imported By | Decision | Reason |
|:---|:---|:---|:---|:---|
| `medicare/medicare/nodes.py` | No | `tests/test_medicare_router.py` | **Delete** | Legacy dummy shim from initial prototype before compiled LangGraph was introduced. |
| `medicare/speech/stt.py` | No | None | **Delete** | Prototype mock Speech-To-Text service not wired to active UI or API gateway. |
| `medicare/speech/tts.py` | No | None | **Delete** | Prototype mock Text-To-Speech service not wired to active UI or API gateway. |
| `medicare/runtime/interrupt.py` | No | None | **Delete** | Prototype human-in-the-loop interruption experiment superseded by LangGraph checkpointer. |
| `medicare/runtime/budget.py` | No | None | **Delete** | Unused step counter prototype superseded by LangGraph recursion limits. |
| `medicare/tools/calculator.py` | No | `tests/test_tools.py` | **Move to tests/support** | General template tool not used by healthcare agents; preserved as test double. |
| `medicare/tools/cloud_kb.py` | No | `tests/test_tools.py` | **Move to tests/support** | Template AWS Bedrock mock tool not used by healthcare agents; preserved as test double. |
| `medicare/tools/mcp_client.py` | No | `tests/test_tools.py` | **Move to tests/support** | Template remote MCP client not used by healthcare agents; preserved as test double. |
| `medicare/tools/search.py` | No | `tests/test_tools.py` | **Move to tests/support** | Generic web search tool not used by healthcare agents; preserved as test double. |
| `medicare/tools/vector_store.py` | No | `tests/test_tools.py` | **Move to tests/support** | Generic mock corporate vector store superseded by `medicare.rag`; preserved as test double. |
| `medicare/tools/weather.py` | No | `tests/test_tools.py` | **Move to tests/support** | Generic weather lookup tool not used by healthcare agents; preserved as test double. |
| `medicare/tools/db_tools.py` | **Yes** | `routing.py`, `nodes_sql.py`, `mock_engine.py` | **Keep in tools/** | Active dynamic database schema and catalog discovery engine. |
| `medicare/tools/sql_query.py` | **Yes** | `hospital_sql_agent.py`, `deps.py`, `nodes_sql.py` | **Keep in tools/** | Production sandboxed SQLite query tool with read-only enforcement. |
| `medicare/tools/policy_search.py`| **Yes** | `policy_rag_agent.py`, `deps.py`, `nodes_policy.py`| **Keep in tools/** | Production policy semantic and BM25 retrieval tool. |
| `medicare/providers/mock_engine.py` | **Yes** | `router.py` | **Keep in providers/** | Production fallback engine when Groq is rate-limited or offline. |
| `medicare/storage/thread_catalog.py`| **Yes** | `checkpointer.py`, `routes/threads.py` | **Keep in storage/** | Provides title generation and tenant isolation validation for threads. |

---

## 2. Structural Decisions

1. **Layering Separation:**
   - `ui/` must never import from `medicare/`. A dedicated `ui/config.py` loads `config/app.yaml` directly, and UI formatting helpers are self-contained.
   - Core platform subsystems (`rag/`, `tools/`, `providers/`, `security/`, `runtime/`, `storage/`, `domain/`) must never import from `agents/`, `api/`, or `medicare/`.
   - Domain contracts (`TableResult`, `Citation`, `SQLAttempt`, `SupervisorPlan`) are consolidated in `medicare.domain.models` and re-exported in `medicare.medicare.state` for backwards compatibility.
   - `sql_query.py` and `policy_search.py` import domain contracts exclusively from `medicare.domain.models`.
2. **Runtime State Separation (`var/`):**
   - `data/` contains ONLY immutable inputs: `seed/` and `policies/`.
   - All runtime SQLite databases (`hospitals.db`, `platform.db`, `manifest.db`, `langgraph_checkpoints.db`), vector stores (`chroma/`), and uploaded files (`uploads/`) are isolated in `var/`.
3. **Packaging of Dataset & Evals:**
   - `medicare/schema.py`, `csv_import.py`, `policy_indexer.py`, and setup CLI move to `medicare/medicare/dataset/`.
   - Shims at `medicare/medicare/setup.py` and `medicare/medicare/evals.py` ensure existing CLI entrypoints remain 100% compatible.
   - Console scripts `medicare-setup` and `medicare-evals` added to `pyproject.toml`.
4. **Documentation Consolidation:**
   - Root `SYSTEM_REFERENCE.md` moved to `docs/reference.md`.
   - Architectural specifications and engineering blueprints consolidated into `docs/decisions/`.
