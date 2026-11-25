# LangGraph Multi-Agent Architecture & RAG Migration Record

This document records the design decisions, architectural mappings, and migration details for transitioning MediCare / MediCare Navigator from sequential imperative async functions to a production-grade LangGraph multi-agent system with multi-format RAG and grounding verification.

---

## 1. Before vs. After Mapping

| Architectural Component | Legacy Implementation | LangGraph Target Implementation |
|---|---|---|
| **Pipeline Orchestration** | Imperative async functions in `nodes.py` called sequentially in `invoke()` and duplicated in `stream()`. | Compiled LangGraph `StateGraph` with parallel fan-out (`Send` / multi-edge) and bounded cyclic sub-graphs. |
| **Code Path Duplication** | Separate `invoke()` (awaited) and `stream()` (SSE yielded) imperative flows. | Single execution path: `invoke()` consumes the graph stream and yields the final message. |
| **Supervisor & Routing** | Pure regex/keyword string matching in `prompts.py` and `mock_engine.py`. | LLM-based structured JSON planning (`SupervisorPlan`) with automatic single-repair, rules cross-check, entity canonicalization via `difflib`, and multi-turn carry-over. |
| **SQL Agent** | Simple while-loop in `nodes.py` (up to 3 retries). | Compiled LangGraph sub-graph (`SQLAgentGraph`) with pre-execution static validation (`static_check`), repeated-query detection, dynamic broadening on 0-rows, and max 1+3 retry enforcement. |
| **Policy Agent & RAG** | Naive Markdown-only chunking, single Chroma dense query without relevance verification. | Corrective Agentic RAG sub-graph (`PolicyAgentGraph`): Multi-format ingestion (PDF, DOCX, MD, TXT, HTML, CSV), hybrid dense + BM25 search with Reciprocal Rank Fusion (RRF), chunk grading, indirect prompt-injection filtering, and query rewriting. |
| **Grounding Verification** | None; hallucinated figures or mismatched clauses passed straight to the user. | Pure functional Grounding Verifier node: Validates numeric facts against evidence, verifies `[Cn]` citations, checks entity presence, with 1 repair regeneration and deterministic fallback. |
| **Tenant Isolation for Docs** | No user uploads; global static folder only. | REST API `/documents` with multipart upload, magic-byte validation, streaming size checks, user-scoped storage, and strict query isolation (`scope == 'curated' OR (scope == 'user' AND user_id == <caller>)`). |

---

## 2. Key Design Decisions

### 2.1 State Representation
- **State Type:** `TypedDict` (`NavigatorState`) is used as the top-level state container for LangGraph compatibility, while sub-entities (`SupervisorPlan`, `SQLAgentResult`, `PolicyAgentResult`, `GroundingReport`, `Citation`, `TableResult`, `ChartSpec`) are strict Pydantic v2 models.
- **Reducers:**
  - `trace: Annotated[list[TraceEntry], operator.add]` for thread-safe timeline updates from parallel workers.
  - `timings: Annotated[dict[str, float], merge_dicts]` for aggregating per-node execution latencies.
  - `llm_calls: Annotated[int, operator.add]` for monitoring budget and step limits.
  - Isolated worker keys: `sql_result` and `policy_result` are written to distinct keys by the parallel workers, eliminating write-write state collisions.

### 2.2 Parent Graph vs. Sub-Graphs
- The parent graph (`MediCareGraph`) orchestrates high-level concerns: Guardrail $\to$ Supervisor $\to$ Parallel Worker Fan-out $\to$ Synthesizer $\to$ Grounding Verifier $\to$ Finalize.
- The workers (`SQLAgentGraph` and `PolicyAgentGraph`) are compiled independently as reusable `StateGraph` instances:
  - This allows standalone agents (`hospital-sql`, `policy-rag`) to execute the exact same sub-graphs as thin wrappers.
  - Worker execution nodes in the parent graph invoke sub-graph streams, forwarding custom progress events (`agent_status`, `retry`, `rewrite`) seamlessly to the parent SSE writer.

### 2.3 Checkpointing Strategy
- **Persistence Engine:** MediCare's existing dual-tier persistence layer (`SqliteCheckpointer` and `SqliteMemoryStore`) remains the single source of truth for conversational history and user memory across sessions.
- **LangGraph Checkpointer:** Configurable via `LANGGRAPH_CHECKPOINTER` (`memory`, `sqlite`, `none`). Uses a per-run compound thread key `f"{thread_id}:{run_id}"` so that intra-run graph states are checkpointed without double-appending conversation turns to the user's thread history.

### 2.4 Vector Store & Multi-Format Ingestion
- **Hybrid Search:** Combines dense cosine similarity embeddings (Chroma ONNX MiniLM or Hash fallback) with sparse BM25 indexing via `rank-bm25`.
- **Fusion:** Scores fused using Reciprocal Rank Fusion (RRF with $K=60$), followed by token-set Jaccard near-duplicate suppression.
- **Document Scopes:**
  - `curated`: System-wide official hospital and policy documents loaded from `data/policies/`.
  - `user`: Authenticated user uploads stored under `data/uploads/<user_id>/<doc_id>/`.

---

## 3. Adapted Existing Tests
*(This table documents any existing tests adapted due to internal structural refactoring. Behavioral assertions are preserved.)*

| Test File | Test Name | Nature of Change | Justification |
|---|---|---|---|
| None yet | - | - | - |

---

## 4. Known Limitations & Assumptions
- Scanned PDF OCR is disabled by default (`ENABLE_OCR=False`) to avoid hard dependencies on system binaries (`tesseract`). Scanned PDFs with no text layer return a friendly `NoExtractableTextError`.
- ChromaDB and SQLite operate in single-process mode; Docker and local deployments should run the FastAPI gateway with a single uvicorn worker.
