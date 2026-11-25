# Dynamic Tool-Calling Architecture & Implementation Decisions

This document records the design decisions, audit findings, and migration steps for making MediCare Navigator fully dynamic, eliminating all static domain data (cities, hospitals, procedures, insurers, prices, sample questions), and delegating entity resolution and query formulation to dynamic AI tool-calling loops.

---

## 1. Audit of Static Domain Data

A repository-wide audit of `medicare/` and `ui/` identified the following locations containing static domain constants:

| File | Static Elements Found | Action Taken |
|---|---|---|
| `medicare/medicare/graph/routing.py` | `CITIES_LIST`, `INSURERS_LIST`, `PROCEDURES_LIST`, keyword routing rules, static procedure partials. | Removed all static lists. Keyword router replaced by dynamic Supervisor LLM prompt with generic fallback; entity resolution removed from router and delegated to worker tool loops (`lookup_values`). |
| `medicare/medicare/schema.py` | Comment strings and docstrings containing `'Ahmedabad'`, `'Mumbai'`, `'Star Health'`, `'Cataract Surgery'`. | Replaced static schema text with dynamic `get_schema()` tool that inspects live SQLite tables, types, foreign keys, and 3 sample rows. |
| `medicare/medicare/prompts.py` | Example queries and few-shot examples referencing specific cities (`Ahmedabad`, `Mumbai`), insurers (`Star Health`, `HDFC ERGO`), and procedures (`Cataract Surgery`, `Cardiac Bypass`). | Replaced all domain-specific examples with neutral placeholders (`<city>`, `<procedure>`, `<insurer>`). |
| `medicare/medicare/graph/nodes_parent.py` | Entity carry-over checks matching explicit city names (`Ahmedabad`, `Mumbai`, etc.) and procedure names; conversational greeting with static questions. | Removed static list checks. Carry-over is handled by conversational LLM context. Greetings explain system capabilities without static hospital names. |
| `medicare/medicare/graph/verify.py` | Static `POLICY_VOCABULARY` and fallback hospital figures in `build_deterministic_fallback`. | Moved generic policy vocabulary to `config/intent_words.yaml`. Fallback on no-LLM mode strictly performs document search without fabricating hospital data. |
| `medicare/rag/ingest.py` | `_infer_insurer_from_path` containing static list of insurer candidate strings. | Replaced with dynamic lookup matching known insurers from SQLite `insurer_acceptance` or manifest metadata. |
| `medicare/tools/policy_search.py` | Static list of known insurers for query filtering. | Replaced with dynamic query to `list_document_filters()`. |
| `ui/components/sample_questions.py` | Static list of static sample question chips. | Deprecated static list. Sample questions are generated dynamically via `GET /medicare/suggestions` from live database and index contents. |
| `ui/components/sidebar.py` | Static curated document filter names. | Replaced with dynamic document list from `GET /documents`. |

---

## 2. Core Architectural Decisions

### 2.1 The One Rule: Zero Domain Values in Code
- **Rule:** Data values (cities, hospitals, insurers, procedures, prices, policy filenames) must **never** appear as string literals in production application code (`medicare/`, `ui/`).
- **Configuration Boundary:** Allowed in configuration files (`config/*.yaml`):
  - `config/guardrails.yaml`: Regex threat patterns for acute emergencies, self-harm, SQL injections, and PII redaction.
  - `config/intent_words.yaml`: Generic intent classification vocabulary (e.g. conversational greetings, question words, helpline constants).
  - `config/medicare_exposure.yaml`: Hidden tables and column exposure allowlist.

### 2.2 Tool Layer Specification (`medicare/tools/`)
All tools expose JSON schema definitions, validate input arguments, and return typed results:
1. `get_schema()`:
   - Reads tables, columns, types, foreign keys from live SQLite database.
   - Fetches 3 sample rows for each exposed table.
   - Caches schema; auto-refreshes when database file modification time (`mtime`) changes.
   - Filters out hidden tables/columns defined in `config/medicare_exposure.yaml`.
2. `lookup_values(table: str, column: str, text: str, limit: int = 8)`:
   - Searches distinct values in the specified table and column using substring and fuzzy matching (`difflib`).
   - Returns exact stored database spellings.
   - Rejects unexposed tables or columns.
3. `run_sql(query: str)`:
   - Hardened read-only execution in sandbox SQLite connection.
   - Dynamic allowlist: Allowed tables and columns are computed dynamically from `get_schema()`.
   - Enforces read-only AST, no stacked queries, no sqlite_master access, row cap.
4. `search_documents(query: str, insurer: str | None, scope: str = "both")`:
   - Hybrid dense vector + sparse BM25 retrieval with Reciprocal Rank Fusion (RRF $K=60$).
5. `list_document_filters()`:
   - Returns distinct insurers and document types currently present in the document store.

### 2.3 Provider Tool Calling Architecture (`medicare/providers/`)
- Unified `chat(messages, tools, tool_choice="auto") -> ModelResponse`:
  - Implemented for `GroqProvider` using OpenAI-compatible function calling API.
  - Validated on `openai/gpt-oss-120b`.
  - Implemented for `ScriptedProvider` for offline deterministic testing.
  - Graceful validation error recovery: Schema validation errors are fed back as tool messages to the model.

### 2.4 Bounded Tool-Calling Loops in LangGraph Sub-Graphs
- **SQL Worker Loop:**
  1. Call model with tools: `get_schema`, `lookup_values`, `run_sql`.
  2. Model queries schema $\to$ resolves entities via `lookup_values` $\to$ executes `run_sql`.
  3. If SQL error occurs, error message is fed back to model for self-correction.
  4. Bounds: at most 3 failed `run_sql` retries, max 6 steps (`AGENT_MAX_STEPS`).
- **Policy Worker Loop:**
  1. Call model with tools: `list_document_filters`, `search_documents`.
  2. Model checks available filters $\to$ searches documents $\to$ rewrites query on weak hits.
  3. Bounds: max 6 steps (`AGENT_MAX_STEPS`).
- **Supervisor AI:**
  - Classifies route (`conversational`, `data`, `policy`, `both`, `clarify`) and rewrites question.
  - Does NOT resolve domain entities in code; entity resolution is strictly performed by worker tools.

### 2.5 No-LLM Fallback Strategy
- When no API key is provided or the provider is unreachable:
  - The app executes `search_documents(user_question)` directly.
  - Displays matching policy excerpts with citations.
  - Informs the user clearly: *"Notice: The AI provider is currently offline or unavailable. Hospital database cost comparisons cannot be computed without an active language model."*
  - No synthetic/fake hospital database numbers are emitted.

---

## 3. Live LLM Validation Summary (openai/gpt-oss-120b on Groq)

- **Dynamic Suggestions Endpoint (`GET /medicare/suggestions`):**
  - Generated live suggestions from SQLite and index:
    1. *"Compare Total Hip Replacement costs across hospitals in Ahmedabad and check Niva Bupa Health Insurance cashless acceptance"*
    2. *"Which hospitals in Ahmedabad have the shortest wait for Total Hip Replacement?"*
    3. *"What are the common waiting periods and claim appeal steps under Niva Bupa Health Insurance?"*
- **End-to-End Execution Trace:**
  - **Dynamic Chip Query:** *"Compare Total Hip Replacement costs across hospitals in Ahmedabad and check Niva Bupa Health Insurance cashless acceptance"*
    - Route: `both` (Supervisor LLM)
    - Entities: Dynamically resolved `city: "Ahmedabad"`, `procedure: "Total Hip Replacement"`, `insurer: "Niva Bupa Health Insurance"`.
    - SQL Worker: Dynamic schema lookup $\to$ executed `SELECT` query on `hospitals` and `hospital_procedures` $\to$ returned comparative table (₹1,63,000–₹2,87,000, 4–6 day wait).
    - Policy Worker: Filtered documents for Niva Bupa $\to$ retrieved cashless terms.
    - Grounding: Grounding verifier verified all numeric claims against the query result table.
  - **Messy Query 1 (Ambiguous procedure):** *"cheapest option under 3 lakh with a short wait in Ahmedabad"*
    - Handled via `clarify` route: *"Could you specify which medical procedure you are interested in?"*
  - **Messy Query 2 (Pre-existing rejection):** *"my claim was rejected because of pre-existing condition what can I do?"*
    - Handled via `policy_only` route: Grounded explanation of waiting periods and the insurer grievance/appeal protocol.
  - **No-LLM Fallback Query:** Verified with mock failing provider; correctly returned document excerpts with clear unavailability notice and 0 errors.

---

## 4. Test Verification Suite Status

- `tests/medicare/test_dynamic_config.py`: **PASSED** (0 occurrences of domain values in AST of `medicare/` and `ui/`).
- `tests/test_dynamic_data.py`: **PASSED** (Full graph executed against invented second dataset Atlantis/Poseidon with zero code changes; dynamic insertion of new rows updates answers automatically).
- `tests/test_dynamic_tools.py`: **PASSED** (Schema refresh on DB mtime change, fuzzy lookup, exposure rejection).
- Full suite: **117 tests passed out of 117**.
- Ruff: **Clean** (`ruff check .` passed, `ruff format --check .` passed).
