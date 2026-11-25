# MediCare & Claim Navigator Architecture Decisions & Log

## Log of Key Architectural Decisions

1. **Default Agent Switching to `medicare-navigator`:**
   - **Requirement:** Set `DEFAULT_AGENT = "medicare-navigator"` in `config.py` and `.env.example`.
   - **Existing Tests:** Updated `tests/test_config.py` and `tests/test_api_endpoints.py` to assert `medicare-navigator` as default agent, while preserving full capability and test coverage for all other 10 agents.

2. **Zero Framework Policy (No LangGraph / LangChain):**
   - MediCare uses an explicit native async state-machine engine on top of `BaseAgent`, `ExecutionEngine`, and typed Pydantic models (`NavigatorState`).
   - The 5-node pipeline (`Guardrail -> Router -> Policy RAG + Hospital SQL -> Synthesizer`) is implemented as modular, isolated async functions operating on `NavigatorState`.

3. **ChromaDB Primary with Zero-Crash Hash-Store Fallback:**
   - ChromaDB `PersistentClient` is used as the primary vector store for policies.
   - If ChromaDB initialization fails or is unavailable in certain environments, `PolicySearchTool` automatically degrades to an internal hash-embedding vector store without throwing an unhandled exception.

4. **SQL Security & Hardened Sandbox:**
   - Read-only connection: `file:{path}?mode=ro`, `uri=True`.
   - Single-statement enforcement via syntax validation and splitting checks.
   - `sqlite3.set_authorizer` installed with strict table, column, and function allowlists.
   - `SQL_MAX_ROWS` row cap and `set_progress_handler` timeout protection.

5. **Self-Correcting SQL Loop Bounds:**
   - Maximum 4 executions total: 1 initial attempt + up to 3 fix retries.
   - Emits custom SSE events on channel `agent_status` with `retry` index.
   - Repeated identical SQL queries between attempts are detected and re-prompted.

6. **Guardrail Categories & Redaction:**
   - Backward-compatible extension to `evaluate_guardrails`: returns `(is_safe, violations)` matching the existing signature while adding `sql_injection`, `pii`, `self_harm`, `medical_emergency`, and `medical_advice_boundary`.
   - `redact_pii(text)` utility provided to scrub Aadhaar, PAN, phone numbers, and email before writing to checkpoints or logs.
   - Immediate non-judgmental crisis response with Tele-MANAS (14416) and 112 for self-harm intent.

7. **Currency Formatting:**
   - Indian numbering system format: `₹1,25,000` via pure Python `format_inr()` with unit tests.

8. **ScriptedProvider Test Double:**
   - Test double implementing `ModelProviderProtocol` that yields sequential predetermined responses, allowing deterministic unit testing of self-correcting retry sequences.

9. **ChatMessage Type Literal Adherence:**
   - Adhered strictly to `ChatMessage(type=Literal['human', 'ai', 'tool', 'custom'])` by embedding system guidelines inside human messages with clear headers (`[SYSTEM INSTRUCTION]`), preventing runtime schema validation errors.

10. **SSE Event Protocol Integration:**
    - Seamlessly integrated custom `agent_status` events into the existing EventSourceResponse pipeline without breaking clients consuming standard token/message streams.

11. **Docker Environment & Packaging:**
    - Host system has no native Docker daemon installed.
    - Configured multi-stage non-root `Dockerfile` and `docker-compose.yml` featuring one-shot `medicare-init` service with read-only host bind mounts (`./data/seed:/app/data/seed:ro` and `./data/policies:/app/data/policies:ro`), healthcheck dependencies, and named volume persistence.
