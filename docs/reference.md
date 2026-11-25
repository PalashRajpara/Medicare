# MediCare: Complete Architectural & Implementation Reference Manual

> **Purpose of this Document:**
> This document is an exhaustive, self-contained, production-grade reference manual for the **MediCare Multi-Agent AI Service Platform** and its flagship production implementation, **MediCare & Claim Navigator AI**. It provides software engineers and autonomous AI agents with complete architectural context, domain models, execution lifecycles, streaming protocols, security policies, multi-agent topologies, tool specifications, API contracts, persistence engines, and guidelines for maintenance, debugging, and extension without requiring access to prior chat context.

---

## Table of Contents
1. [System Overview & Architecture](#1-system-overview--architecture)
2. [Complete Directory & File Manifest](#2-complete-directory--file-manifest)
3. [Configuration & Environment Specification](#3-configuration--environment-specification)
4. [Domain Models, Contracts & Protocols](#4-domain-models-contracts--protocols)
5. [Security, Guardrails & Parameter Sanitization](#5-security-guardrails--parameter-sanitization)
6. [Dual-Tier Persistence & Thread State Engine](#6-dual-tier-persistence--thread-state-engine)
7. [Provider Routing & Mock Engine](#7-provider-routing--mock-engine)
8. [The MediCare Multi-Agent Team & Topologies](#8-the-medicare-multi-agent-team--topologies)
9. [Operational Tools Subsystem](#9-operational-tools-subsystem)
10. [API Gateway & Server-Sent Events (SSE) Protocol](#10-api-gateway--server-sent-events-sse-protocol)
11. [Standardized AG-UI Protocol Bridge](#11-standardized-ag-ui-protocol-bridge)
12. [Streamlit User Interface Specification](#12-streamlit-user-interface-specification)
13. [Automated Verification & Test Suite](#13-automated-verification--test-suite)
14. [Deployment & Containerization](#14-deployment--containerization)
15. [Extension Guide for Autonomous AI Engineers](#15-extension-guide-for-autonomous-ai-engineers)

---

## 1. System Overview & Architecture

**MediCare** is an enterprise-grade multi-agent AI execution platform. It decouples conversational agent topology design from execution state management, providing persistent multi-turn memory, real-time dual-mode token and event streaming, pre-execution safety guardrails, human-in-the-loop interruption, and multimodal voice interaction.

The platform is purpose-built to host specialized, multi-node agent teams. Its flagship deployment is the **MediCare & Claim Navigator AI**, an intelligent assistant that empowers patients and policyholders with hospital cost discovery, wait-time intelligence, cashless/claim guidance, and insurance policy clause interpretation.

### 1.1 Architectural Topology

```
 +-------------------------------------------------------------------------+
 |                      Web Client UI (Streamlit)                          |
 |  - Dedicated MediCare & Claim Navigator Workspace                       |
 |  - Active LLM Backend Status Badge (openai/gpt-oss-120b)                |
 |  - Typewriter Token Streaming & Markdown/Table/Chart Rendering          |
 |  - Sample Query Quick Chips & Execution Audit Accordions                |
 +-----------------------------------+-------------------------------------+
                                     |
                                     | HTTP REST / SSE Stream
                                     v
 +-------------------------------------------------------------------------+
 |                      MediCare Gateway (FastAPI)                       |
 |  - Bearer Auth Middleware & Model Allowlist Validation                  |
 |  - Reserved Parameter Interception                                      |
 |  - Endpoints: /info, /health, /invoke, /stream, /history, /threads,     |
 |               /feedback, /agui/run, /medicare/status                    |
 +-----------------------------------+-------------------------------------+
                                     |
                                     v
 +-------------------------------------------------------------------------+
 |                      Execution Runtime Engine                           |
 |  - Dynamic Agent Registry (MediCare Multi-Agent Team)                   |
 |  - Clinical Safety Guardrails (Prompt Injection, Emergencies, PII)      |
 |  - Multi-Turn Intent Router (conversational, data_only, policy_only,    |
 |    both) with entity carry-over across turns                            |
 |  - Self-Correcting SQL Loop & Grounded Policy Citation Engine           |
 +-------------------+---------------------------------+-------------------+
                     |                                 |
         Read/Write  |                     Call/Return |
         State       v                                 v
 +-----------------------------------+     +-------------------------------+
 |     Dual-Tier Persistence         |     | External Services & Models    |
 |  - Checkpoints: SQLite / In-Memory|     |  - Groq (openai/gpt-oss-120b) |
 |  - Cross-Turn Memory: User Store  |     |  - Mock Engine (Offline CI)   |
 |  - Thread Catalog & Auto-Titling  |     |  - ChromaDB / BM25 Store      |
 +-----------------------------------+     |  - Read-Only Hospital SQLite  |
                                           +-------------------------------+
```

### 1.2 Core Architectural Principles
1. **Decoupled Execution & Topology:** Agents inherit from `BaseAgent`. The runtime engine manages thread persistence, context propagation, and event demultiplexing.
2. **Dual-Tier State Storage:**
   - *Short-Term Checkpointing:* Immutable execution snapshots capturing conversation history, tool outputs, and execution graph steps indexed by `thread_id`.
   - *Long-Term Cross-Thread Memory:* User-scoped namespace-isolated key-value stores (`(user_id,) -> key -> value`) that persist across distinct sessions.
3. **Controlled Multi-Node Pipelines:** Rather than unpredictable open-loop agent tool calling, complex clinical queries execute through a deterministic 5-node pipeline with dedicated self-correction loops.
4. **Strict Grounding & Zero-Hallucination:** Cost data must originate strictly from verified SQLite records; policy terms and waiting periods must be grounded in indexed policy documents with citations.
5. **Zero-Crash Graceful Degradation:** When offline, in testing environments, or missing external credentials, the platform seamlessly falls back to local deterministic mock engines and synthetic stores.

---

## 2. Complete Directory & File Manifest

```
medicare/
├── pyproject.toml                         # Project metadata, dependencies, tool configurations (Ruff, Pytest)
├── .gitignore                             # Git ignore rules for virtualenvs, caches, databases
├── .env.example                           # Documented environment variable template
├── README.md                              # Public repository documentation & quickstart
├── Dockerfile                             # Multi-stage production container build
├── docker-compose.yml                     # Multi-service local deployment (Gateway + UI)
├── CLEAN_SPEC.md                          # Frozen system specification
├── IMPLEMENTATION_PLAN.md                 # Architecture blueprint and execution plan
├── SYSTEM_REFERENCE.md                    # This master reference document
│
├── medicare/                           # Core Platform Package
│   ├── __init__.py                        # Package export and version definition (0.1.0)
│   ├── config.py                          # Pydantic Settings configuration schemas and validation
│   │
│   ├── domain/                            # Core domain models, typed exceptions, and protocols
│   │   ├── __init__.py
│   │   ├── models.py                      # ChatMessage, Thread, Checkpoint, TaskEvent, Feedback
│   │   ├── errors.py                      # Domain-specific typed exceptions
│   │   └── protocols.py                   # CheckpointStore, MemoryStore, and ModelProvider protocols
│   │
│   ├── security/                          # Security, authentication, and moderation guardrails
│   │   ├── __init__.py
│   │   ├── auth.py                        # Bearer token verification middleware
│   │   ├── sanitization.py                # Reserved parameter collision & model allowlist validation
│   │   └── guardrails.py                  # Prompt injection, override, and role manipulation detector
│   │
│   ├── storage/                           # Persistence layer engines
│   │   ├── __init__.py
│   │   ├── checkpointer.py                # Thread checkpointing engine (SQLite, In-Memory)
│   │   ├── memory_store.py                # Hierarchical key-value store for user cross-session facts
│   │   └── thread_catalog.py              # Thread indexer, tenant isolation, and auto-titling (<=60 chars)
│   │
│   ├── providers/                         # Foundational model routing & testing engines
│   │   ├── __init__.py
│   │   ├── router.py                      # Multi-provider router (Groq, OpenAI, Anthropic, Ollama)
│   │   └── mock_engine.py                 # Deterministic mock engine for offline testing & CI
│   │
│   ├── tools/                             # Operational tool implementations
│   │   ├── __init__.py
│   │   ├── base.py                        # BaseTool contract and function-calling schema generator
│   │   ├── search.py                      # DuckDuckGo search integration with fallback knowledge
│   │   ├── calculator.py                  # Isolated AST math evaluator with constants (pi, e)
│   │   ├── weather.py                     # Weather lookup with fallback simulation
│   │   ├── vector_store.py                # Semantic vector store for corporate policies & RAG
│   │   ├── cloud_kb.py                    # Cloud knowledge base adapter (AWS Bedrock KB abstraction)
│   │   ├── db_tools.py                    # Dynamic DB schema and catalog introspection
│   │   ├── sql_query.py                   # SQLiteQueryTool with read-only connection & row caps
│   │   └── policy_search.py               # PolicySearchTool for ChromaDB / BM25 insurance clauses
│   │
│   ├── runtime/                           # Execution engine, context, and event demultiplexer
│   │   ├── __init__.py
│   │   ├── context.py                     # Execution context and UUIDv7 run ID generator
│   │   ├── engine.py                      # State machine execution engine & checkpoint orchestrator
│   │   └── events.py                      # SSE stream encoders (token, message, custom, done)
│   │
│   ├── agents/                            # MediCare Multi-Agent Team Implementations
│   │   ├── __init__.py
│   │   ├── base.py                        # BaseAgent abstract contract
│   │   ├── registry.py                    # Dynamic agent registry and lookup
│   │   ├── medicare_navigator.py          # Primary Supervisor: 5-Node Clinical & Policy Assistant
│   │   ├── hospital_sql_agent.py          # Standalone Hospital SQL Query Loop Agent
│   │   └── policy_rag_agent.py            # Standalone Insurance Policy RAG Retrieval Agent
│   │
│   ├── medicare/                          # MediCare Subsystem Core
│   │   ├── __init__.py
│   │   ├── chart.py                       # Dynamic ChartSpec generator for cost comparisons
│   │   ├── dataset/                       # Dataset management and CLI
│   │   │   ├── __init__.py
│   │   │   ├── cli.py                     # Command-line database and index initialization script
│   │   │   ├── csv_import.py              # Idempotent seed data CSV loader
│   │   │   ├── policy_indexer.py          # Policy document chunker and ChromaDB indexer
│   │   │   └── schema.py                  # SQLite DDL, table/column allowlists, schema prompts
│   │   ├── evals/                         # Golden benchmark evaluation suite
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py                # CLI runner entrypoint
│   │   │   ├── cli.py                     # CLI argument parser
│   │   │   └── runner.py                  # Evaluation execution harness and report generator
│   │   ├── graph/                         # Compiled LangGraph Multi-Agent Workflows
│   │   │   ├── __init__.py
│   │   │   ├── build.py                   # StateGraph assembly and compilation
│   │   │   ├── deps.py                    # Dependency injection container
│   │   │   ├── events.py                  # Node execution event dispatchers
│   │   │   ├── nodes_parent.py            # Supervisor routing and synthesis nodes
│   │   │   ├── nodes_policy.py            # Corrective RAG nodes
│   │   │   ├── nodes_sql.py               # Self-correcting SQL nodes
│   │   │   ├── policy_subgraph.py         # Policy RAG sub-graph definition
│   │   │   ├── routing.py                 # Pure routing functions
│   │   │   ├── sql_subgraph.py            # Hospital SQL sub-graph definition
│   │   │   ├── state.py                   # NavigatorState, SQLAttempt, Citation, TableResult
│   │   │   └── verify.py                  # Pure grounding verifier & fallback synthesizer
│   │   ├── prompts.py                     # Compatibility shim for prompt callers
│   │   ├── schema.py                      # Compatibility shim
│   │   ├── setup.py                       # Compatibility shim
│   │   └── state.py                       # Compatibility shim
│   │
│   ├── api/                               # FastAPI Gateway & REST/SSE Endpoints
│   │   ├── __init__.py
│   │   ├── app.py                         # App factory, lifespan, CORS, and exception handlers
│   │   └── routes/                        # Route handlers (one file per router)
│   │       ├── __init__.py
│   │       ├── agui.py                    # POST /agui/{agent_id}/run, POST /agui/run
│   │       ├── documents.py               # POST /documents/upload, GET /documents
│   │       ├── feedback.py                # POST /feedback
│   │       ├── info.py                    # GET /info, GET /health
│   │       ├── invoke.py                  # POST /{agent_id}/invoke, POST /invoke
│   │       ├── medicare.py                # GET /medicare/status
│   │       ├── stream.py                  # POST /{agent_id}/stream, POST /stream (SSE)
│   │       └── threads.py                 # POST /history, GET /threads
│   │
│   └── telemetry/                         # Observability & Tracing
│       ├── __init__.py
│       └── tracer.py                      # Observability trace dispatcher & run feedback store
│
├── ui/                                    # Streamlit Production Frontend
│   ├── __init__.py
│   ├── app.py                             # Multi-page router, styles, shared sidebar
│   ├── client.py                          # Synchronous & streaming backend HTTP/SSE client
│   ├── config.py                          # Independent UI configuration loader
│   ├── state.py                           # Session state manager & typed helpers
│   ├── styles.css                         # Clean healthcare CSS styling
│   ├── pages/
│   │   ├── chat.py                        # Interactive chat with stepper, streaming, tabs
│   │   ├── documents.py                   # Document upload, live polling, deletion
│   │   └── how_it_works.py                # Plain-language roles, Mermaid diagrams, telemetry
│   └── components/
│       ├── answer.py                      # Unified assistant answer renderer
│       ├── banners.py                     # Sample data and offline notification banners
│       ├── citations.py                   # [C1] marker parsing and popover chips
│       ├── feedback.py                    # Thumbs evaluation and message actions
│       ├── results_chart.py               # Plotly charts from ChartSpec
│       ├── results_table.py               # Formatted st.dataframe with column_config & CSV export
│       ├── sidebar.py                     # Shared sidebar with search, scope, settings, status
│       ├── stepper.py                     # Live execution stepper (st.status)
│       ├── suggestions.py                 # Empty-state cards, suggestion chips, follow-ups
│       └── trace_panel.py                 # "How I got this" expander (Plan, SQL, Policy, Grounding, Timings)
│
└── tests/                                 # Grouped Test Suite (153 Tests, 100% Passing)
    ├── conftest.py                        # Session path isolation fixture and test harness
    ├── api/                               # API route and SSE streaming tests
    ├── e2e/                               # End-to-end integration tests
    ├── graph/                             # LangGraph parent and sub-graph workflow tests
    ├── medicare/                          # MediCare domain and agent tests
    ├── rag/                               # Chunking, loader, and retrieval tests
    ├── security/                          # Clinical safety and auth guardrail tests
    ├── storage/                           # Checkpointer and memory store tests
    ├── support/                           # Test doubles and fixtures
    ├── tools/                             # Tool sandbox and execution tests
    └── ui/                                # UI client, formatting, AppTest, and voice audit tests
    ├── support/                           # Test doubles, scripted providers, and mock tools
    └── tools/                             # Tool execution and sandbox tests
    ├── test_medicare_chart.py             # ChartSpec builder & INR currency formatting
    ├── test_medicare_navigator_e2e.py     # End-to-end SSE event progression & status metadata
    ├── test_config.py                     # Configuration schema validation tests
    ├── test_security.py                   # Auth, model allowlist, reserved param, and injection tests
    ├── test_storage.py                    # SQLite/Memory checkpointer, memory store, thread catalog
    ├── test_tools.py                      # Calculator, Search, Weather, Vector, Cloud KB, MCP tests
    ├── test_api_endpoints.py              # Endpoints: /info, /health, /invoke, /feedback
    ├── test_streaming.py                  # SSE stream demuxing & token generation tests
    ├── test_threads_and_history.py        # /history, /threads, and tenant isolation tests
    └── test_agui_bridge.py                # AG-UI protocol bridge translation & filtering tests
```

---

## 3. Configuration & Environment Specification

Configuration is managed via Pydantic Settings in `medicare/config.py`, loading from `.env` files or system environment variables.

### 3.1 Settings Fields & Defaults

```python
class Settings(BaseSettings):
    # Server Network & Gateway
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30

    # Security & Authentication (HTTP Bearer token)
    SERVICE_SECRET_KEY: str | None = None

    # Model Defaults & Allowlist
    DEFAULT_AGENT: str = "medicare-navigator"
    DEFAULT_MODEL: str = "mock-gpt-4"
    ALLOWED_MODELS: list[str] = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "mock-gpt-4",
    ]
    USE_MOCK_MODELS: bool = True
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # Cloud & Provider API Keys
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    DEEPSEEK_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    AWS_BEDROCK_ENABLED: bool = False

    # Local Inference & Daemon
    LOCAL_MODEL_URL: str | None = "http://localhost:8000/v1"
    OLLAMA_BASE_URL: str | None = "http://localhost:11434"

    # Persistence
    STORAGE_ENGINE: Literal["sqlite", "memory", "postgres", "mongo"] = "sqlite"
    SQLITE_PATH: str = "var/platform.db"
    POSTGRES_DSN: str | None = None
    MONGO_URI: str | None = None

    # MediCare & Claim Navigator Configuration
    MEDICARE_DB_PATH: str = "var/hospitals.db"
    POLICY_DOCS_DIR: str = "data/policies"
    SEED_CSV_DIR: str = "data/seed"
    CHROMA_PATH: str = "var/chroma"
    CHROMA_COLLECTION: str = "insurance_policies"
    SQL_MAX_RETRIES: int = 3
    SQL_MAX_ROWS: int = 200
    SQL_TIMEOUT_SECONDS: float = 5.0
    RAG_TOP_K: int = 5
    MEDICARE_DEMO_FAIL_FIRST: bool = False
    HELPLINE_EMERGENCY: str = "112"
    HELPLINE_MENTAL_HEALTH: str = "14416 (Tele-MANAS)"

    # External Tools & Integrations
    OPENWEATHER_API_KEY: str | None = None
    CLOUD_KB_ID: str | None = None
    REMOTE_MCP_URL: str | None = None
    REMOTE_MCP_TOKEN: str | None = None

    # Observability & Tracing
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "medicare"
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # Multimodal Voice
    STT_PROVIDER: str = "mock"
    TTS_PROVIDER: str = "mock"
```

### 3.3 Dynamic Configuration & Architecture Registry

To guarantee pure schema agnosticism, domain decoupling, and test reproducibility, the platform externalizes configuration parameters, technical constants, and domain data from `medicare/` and `ui/`:

1. **Category A (Data Values):** Cities, hospitals, insurers, and procedures are NEVER stored in code; all are dynamically read via tools from the database or vector index.
2. **Category B (Schema Agnosticism):** Chart specifications, column classifications, and table formatters dynamically inspect column types without referencing specific column names (`avg_cost_inr`, etc.).
3. **Category C (Domain Vocabulary):** Verifier terms, policy keywords, and rewrite indicators reside in `config/verifier_terms.yaml` and `config/intent_words.yaml`.
4. **Category D (User-Facing Text):** All refusal messages, fallbacks, operational notices, section headers, and UI strings reside in `config/messages.yaml` (loaded via `msg("key", **vars)`) and `config/app.yaml`.
5. **Category E (System Prompts):** All prompts reside in `config/prompts/*.md`, loaded dynamically with `{placeholder}` interpolation and verified on startup.
6. **Category F (Numbers & Limits):** Timeouts, retry counts, row limits, and thresholds are env-driven via `Settings`.
7. **Category G (Environment Constants):** Model names, URLs, and currency symbols (`₹`, `INR`) are driven by `Settings` or `config/app.yaml`.

#### Configuration Files Registry

| File | Controlled Subsystems & Parameters |
|---|---|
| `config/app.yaml` | Application branding, title, currency symbol/code, UI labels, button text, table/chart headers, mock query templates. |
| `config/messages.yaml` | Refusal messages, fallback notices, error messages, section headings, and verifier issue explanations. |
| `config/verifier_terms.yaml` | Domain policy vocabulary, disclaimer words, exempt numbers for grounding verification. |
| `config/intent_words.yaml` | Conversational greetings, conversational patterns, policy indicators, data indicators, query expansion synonyms. |
| `config/prompts/*.md` | Prompt templates with dynamic `{placeholder}` interpolation and startup validation. |
| `config/config_allowlist.yaml` | Allowlist of technical framework constants (HTTP codes, SSE event types, tool docstrings) with mandatory reasons. |

#### Continuous Integrity Verification

Run the automated configuration and static data validator at any time:

```bash
uv run python scripts/validate_config.py
```

---

## 4. Domain Models, Contracts & Protocols

Located in `medicare/domain/models.py`, `errors.py`, and `protocols.py`.

### 4.1 Domain Entities

```python
class ToolCallDescriptor(BaseModel):
    id: str = Field(default_factory=generate_uuid)
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    type: Literal["human", "ai", "tool", "custom"]
    content: str
    tool_calls: list[ToolCallDescriptor] = Field(default_factory=list)
    tool_call_id: str | None = None
    run_id: str | None = None
    response_metadata: dict[str, Any] = Field(default_factory=dict)
    custom_data: dict[str, Any] = Field(default_factory=dict)


class CheckpointSnapshot(BaseModel):
    checkpoint_id: str = Field(default_factory=generate_uuid)
    thread_id: str
    step_index: int
    channel_values: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Thread(BaseModel):
    thread_id: str
    user_id: str
    agent_id: str
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### 4.2 MediCare Domain Models (`medicare/medicare/state.py`)

```python
class Citation(BaseModel):
    source: str
    section: str
    text: str
    score: float = 0.0


class SQLAttempt(BaseModel):
    attempt: int
    sql: str
    error: str | None = None
    kind: str | None = None
    row_count: int = 0


class TableResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False


class ChartSpec(BaseModel):
    chart_type: Literal["grouped_bar", "bar"]
    data: list[dict[str, Any]]
    x_key: str
    y_keys: list[str]
    title: str
    y_label: str = "Amount (INR)"


class NavigatorState(TypedDict, total=False):
    """Top-level parent graph state with LangGraph channels and reducers."""

    question: str
    history: list[dict[str, Any]]
    user_id: str
    thread_id: str
    run_id: str
    doc_scope: Literal["both", "curated", "mine"]
    guardrail: GuardrailOutcome | None
    plan: SupervisorPlan | None
    sql_result: SQLAgentResult | None
    policy_result: PolicyAgentResult | None
    answer: str
    chart: ChartSpec | None
    grounding: GroundingReport | None
    trace: Annotated[list[TraceEntry], operator.add]
    timings: Annotated[dict[str, float], merge_dicts]
    llm_calls: Annotated[int, operator.add]
    regenerations: int
```

---

## 5. Security, Guardrails & Parameter Sanitization

### 5.1 Bearer Token Verification (`medicare/security/auth.py`)
- When `SERVICE_SECRET_KEY` is set in configuration, all non-health API endpoints enforce authorization:
  `Authorization: Bearer <SERVICE_SECRET_KEY>`.
- Missing or malformed authorization headers raise `AuthenticationRequiredError` (HTTP 401).
- When `SERVICE_SECRET_KEY` is omitted or empty, the auth gate allows traffic through while logging an operational warning.

### 5.2 Reserved Parameter Collision Protection (`medicare/security/sanitization.py`)
- Callers cannot inject internal state machine routing keys via `agent_config`.
- Prohibited reserved keys:
  ```python
  RESERVED_KEYS = frozenset({"thread_id", "user_id", "model", "checkpoint_id", "checkpoint_ns"})
  ```
- Requests attempting to pass any reserved key are intercepted immediately with `ReservedParameterError` (HTTP 422).

### 5.3 Model Allowlist Validation (`medicare/security/sanitization.py`)
- Cross-references requested `model` against `settings.ALLOWED_MODELS`.
- Requests specifying unauthorized models are rejected with `ModelNotAllowedError` (HTTP 400).
- If omitted, defaults safely to `settings.DEFAULT_MODEL`.

### 5.4 Pre-Execution Moderation Guardrails (`medicare/security/guardrails.py` & `medicare/medicare/graph/nodes_parent.py`)
Evaluates input prompts before invoking downstream LLMs or executing queries:
1. **Prompt Injection & Overrides:** Intercepts attempts to override system instructions (`ignore previous instructions`, `reveal your system prompt`, `developer mode`).
2. **SQL Injection Defense:** Rejects raw SQL injection patterns (`UNION SELECT`, `DROP TABLE`, `sqlite_master`, `--`, `/*`) at the guardrail layer.
3. **Medical Emergency Intercept:** Detects acute physical or mental distress (chest pain, stroke symptoms, suicidal ideation) and halts immediately with verified national emergency hotline guidance (`112`, `14416 Tele-MANAS`).
4. **PII Redaction:** Automatically strips or masks Aadhaar numbers, PAN numbers, and telephone numbers from prompt text before LLM dispatch.
5. **Soft Medical Advice Boundary:** Appends mandatory disclaimers clarifying that cost estimations and policy explanations do not constitute medical or insurance underwriting advice.

---

## 6. Dual-Tier Persistence & Thread State Engine

```
+-----------------------------------------------------------------------------------+
|                                  FastAPI Gateway                                  |
|         Receives request with user_id, thread_id, model, and prompt               |
+-----------------------------------------+-----------------------------------------+
                                          |
                     +--------------------+--------------------+
                     |                                         |
                     v                                         v
   +------------------------------------+    +------------------------------------+
   |   Tier 1: Checkpoint Store         |    |   Tier 2: Long-Term Memory Store   |
   |   (Thread History & State)         |    |   (Cross-Thread User Profile)      |
   +------------------------------------+    +------------------------------------+
   | SQLite: ~/.medicare/checkpoints.db   | SQLite: ~/.medicare/memory.db   |
   | Table: `checkpoints`                   | Table: `memories`                  |
   |   - thread_id (UUID/string)            |   - namespace (user_id)            |
   |   - step_index (turn count)            |   - key (e.g., 'insurer', 'city')  |
   |   - channel_values (JSON of messages)  |   - value (JSON blob)              |
   |   - metadata (user_id, timestamps)     |   - updated_at (timestamp)         |
   | Table: `thread_catalog`                |                                    |
   |   - thread_id                          |                                    |
   |   - user_id                            |                                    |
   |   - title (auto-generated from query)  |                                    |
   |   - updated_at                         |                                    |
   +------------------------------------+    +------------------------------------+
```

### 6.1 Short-Term Checkpointing (`medicare/storage/checkpointer.py`)
- **`SqliteCheckpointer`**: Production SQLite checkpointer utilizing `aiosqlite` for asynchronous non-blocking transactions.
  - Automatically migrates database schemas on startup.
  - `checkpoints` table: `(checkpoint_id, thread_id, step_index, channel_values, metadata, created_at)` with compound index `(thread_id, step_index DESC)`.
  - `threads` table: `(thread_id, user_id, agent_id, created_at, updated_at, title)` with index `(user_id, updated_at DESC)`.
- **`InMemoryCheckpointer`**: Zero-dependency ephemeral checkpointer for fast testing and air-gapped CI.

### 6.2 Long-Term User Memory (`medicare/storage/memory_store.py`)
- Hierarchical key-value store indexed by namespaces: `(user_id,) -> key -> value`.
- Stores user profile attributes (e.g., insurer name, preferred city, policy number) that survive across distinct sessions.
- `InMemoryMemoryStore` provides rapid in-memory operations for unit tests.

### 6.3 Thread Catalog & Tenant Isolation (`medicare/storage/thread_catalog.py`)
- **Auto-Titling:** Extracts title from opening human message turn, cleans whitespace, and truncates to $\le 60$ characters.
- **Strict Cross-Tenant Isolation:** `list_threads(user_id, agent_id)` enforces that only checkpoints matching the authenticated user's ID are returned, preventing data disclosure.

---

## 7. Provider Routing & Mock Engine

### 7.1 Router (`medicare/providers/router.py`)
- Decouples agents from concrete model backends.
- When `settings.USE_MOCK_MODELS=True` (default for tests/offline), routes requests to `MockModelEngine`.
- Supports live inference via Groq, OpenAI, Anthropic, Gemini, DeepSeek, Azure OpenAI, and Ollama.
- Automatically handles chat role mapping: converts `human` $\to$ `user` and `ai` $\to$ `assistant` for provider compatibility (e.g. Groq).

### 7.2 Deterministic Mock Engine (`medicare/providers/mock_engine.py`)
Simulates realistic responses and tool execution without live API keys:
- **MediCare Intent Router:** Accurately classifies greetings (`hello`, `hi`) into `"conversational"`, procedure queries into `"data_only"`, policy terms into `"policy_only"`, and combined queries into `"both"`.
- **Conversational Route Handling:** When prompted with `CONVERSATIONAL_PROMPT`, generates a warm introductory welcome highlighting capabilities and starter questions without querying databases.
- **SQL Generation & Synthesis:** Generates valid SQLite queries matching the schema and formats markdown synthesis responses with summary, tables, and citations.
- **Typewriter Token Streaming:** `stream_tokens()` splits response text into word chunks with simulated async delays for real-time typewriter display.

---

## 8. The MediCare Multi-Agent Team & Topologies

The agent catalog is exclusively dedicated to the **MediCare Multi-Agent Team**, registered in `medicare/agents/registry.py`:

```
 +---------------------------------------------------------------------------------+
 |                           MediCare Multi-Agent Catalog                          |
 +----+------------------------+---------------------------------------------------+
 | 1  | medicare-navigator     | 5-Node Clinical & Policy Supervisor Agent         |
 | 2  | hospital-sql           | Standalone Self-Correcting Hospital Query Agent   |
 | 3  | policy-rag             | Standalone Grounded Insurance Policy RAG Agent    |
 +----+------------------------+---------------------------------------------------+
```

### 8.1 MediCare Navigator Supervisor Agent (`medicare/agents/medicare_navigator.py`)
- **Key:** `medicare-navigator` (Default system agent)
- **Architecture:** 5-Node coordinated pipeline:
  ```
  Node 1: Guardrail Node
         │
         ▼
  Node 2: Multi-Turn Intent Router Node
         │
         ├───────────────────────┬───────────────────────┐
         ▼                       ▼                       ▼
  [conversational]         [policy_only]           [data_only]
  Pass-through             Node 3: Policy RAG      Node 4: Hospital SQL
  (No DB / RAG calls)      Vector retrieval        Self-correcting loop
         │                       │                       │
         └───────────────────────┴───────────────────────┘
                                 │
                                 ▼
                   Node 5: Synthesizer Node
                   (Summary, Comparison Table, Citations, Chart)
  ```
- **Intent Routes:**
  1. `conversational`: Casual greetings (`"hello"`, `"hi"`) and general platform questions. Yields a welcoming overview of capabilities with starter prompt suggestions without running SQL or RAG queries.
  2. `data_only`: Hospital procedure costs, doctor consultation fees, bed charges, and wait-time queries.
  3. `policy_only`: Pre-existing disease waiting periods, copays, claim rejection grounds, and maternity benefits.
  4. `both`: Combined cost comparison and insurance claim coverage feasibility.

### 8.2 Hospital SQL Agent (`medicare/agents/hospital_sql_agent.py`)
- **Key:** `hospital-sql`
- **Purpose:** Standalone execution of self-correcting SQL loops over the hospital database.
- **Execution Loop:**
  - *Initial Attempt:* Translates natural language into a SELECT query using `SQL_GENERATOR_PROMPT`.
  - *Self-Correction Loop:* If SQLite throws a syntax error (e.g. unknown column, missing join), the error message is fed back to the model with `SQL_FIXER_PROMPT`.
  - *Retries:* Up to 3 fix retries (4 executions total).
  - *Safety:* Read-only connection, `SQL_MAX_ROWS=200` row cap, timeout enforcement, and schema allowlist validation.

### 8.3 Policy RAG Agent (`medicare/agents/policy_rag_agent.py`)
- **Key:** `policy-rag`
- **Purpose:** Semantic chunk retrieval and clause grounding across indexed health insurance policies.
- **Retrieval Engine:** Queries ChromaDB collection (`insurance_policies`) with BM25 fallback. Filters by insurer if extracted by router.
- **Output:** Returns strictly grounded `Citation` objects with source document names, section titles, and verbatim text.

---

## 9. Operational Tools Subsystem

All tools inherit from `BaseTool` (`medicare/tools/base.py`):

| Tool Name | Module | Description & Capabilities |
| :--- | :--- | :--- |
| `get_schema` | `tools/db_tools.py` | Live SQLite schema introspection tool returning tables, columns, data types, foreign keys, and 3 sample rows. Automatically refreshes on database file mtime change and filters hidden entities based on `config/medicare_exposure.yaml`. |
| `lookup_values` | `tools/db_tools.py` | Fuzzy and substring search over exposed database columns to resolve user entities into exact stored database spellings. |
| `list_document_filters`| `tools/db_tools.py` | Dynamic document filter introspection tool returning all distinct insurers and document types currently indexed. |
| `sqlite_query` | `tools/sql_query.py` | Read-only SQLite query tool with dynamic table and column allowlists computed at runtime from `get_schema()`. Enforces read-only AST, blocks access to `sqlite_master`, caps rows, and self-corrects on syntax errors. |
| `policy_search` | `tools/policy_search.py` | Semantic vector search across health insurance policy clauses using ChromaDB with automatic term-frequency fallback. Returns source file, section, and text. |
| `calculator` | `tools/calculator.py` | Safe AST math evaluator. Disallows arbitrary code or imports. Supports arithmetic (`+`, `-`, `*`, `/`, `**`, `%`, `//`), functions (`sqrt`, `sin`, `cos`, `abs`, `round`, `log`, `exp`), and constants (`pi`, `e`). |
| `web_search` | `tools/search.py` | DuckDuckGo search integration (`DDGS`). Extracts titles, summaries, and source links. Includes verified cached knowledge fallback if network is offline. |
| `weather` | `tools/weather.py` | Real-time weather lookup via OpenWeatherMap API with temperature, description, humidity, and simulated fallback. |
| `cloud_kb_search` | `tools/cloud_kb.py` | Cloud knowledge base retrieval adapter (AWS Bedrock KB) returning ranked excerpts with relevance confidence scores. |
| `mcp_repository_tool` | `tools/mcp_client.py` | Model Context Protocol HTTP client sending authenticated tool requests to remote tool servers. |

---

## 10. API Gateway & Server-Sent Events (SSE) Protocol

Built with FastAPI in `medicare/api/app.py`.

### 10.1 Endpoints Specification

| Endpoint | Method | Auth Required | Purpose |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | No | Infrastructure liveness probe returning `{"status": "ok", "telemetry": "connected"}`. |
| `/info` | `GET` | Yes | System metadata discovery: registered agents (`medicare-navigator`, `hospital-sql`, `policy-rag`), allowed models, defaults. |
| `/{agent_id}/invoke` | `POST` | Yes | Synchronous execution turn against an explicit agent. |
| `/invoke` | `POST` | Yes | Synchronous execution turn against default agent (`medicare-navigator`). |
| `/{agent_id}/stream` | `POST` | Yes | Real-time SSE streaming against an explicit agent. |
| `/stream` | `POST` | Yes | Real-time SSE streaming against default agent (`medicare-navigator`). |
| `/{agent_id}/history` | `POST` | Yes | Reconstructs ordered thread message history. |
| `/history` | `POST` | Yes | Reconstructs ordered thread message history. |
| `/{agent_id}/threads` | `GET` | Yes | Lists conversation sessions for a user within a specific agent. |
| `/threads` | `GET` | Yes | Lists all conversation sessions for a user across agents. |
| `/feedback` | `POST` | Yes | Records qualitative human evaluation ratings ($0.0 \le score \le 1.0$) for a `run_id`. |
| `/agui/{agent_id}/run`| `POST` | Yes | AG-UI standardized protocol execution stream for explicit agent. |
| `/agui/run` | `POST` | Yes | AG-UI standardized protocol execution stream for default agent. |
| `/medicare/status` | `GET` | Yes | Returns database status: hospital count, procedure count, insurer count, policy chunks. |
| `/medicare/suggestions`| `GET` | Yes | Dynamically generates sample question chips from the live database and document index at runtime. |

### 10.2 Server-Sent Events (SSE) Protocol Specification
Streams are delivered with `Content-Type: text/event-stream`.

1. **Token Delta Event (Typewriter Display):**
   ```
   data: {"type": "token", "content": " Cataract"}
   
   ```
2. **Completed Chat Message Event:**
   ```
   data: {"type": "message", "content": {"type": "ai", "content": "...", "response_metadata": {"medicare": {...}}}}
   
   ```
3. **Custom Progress Status Event (`agent_status`):**
   ```
   data: {"type": "custom", "channel": "agent_status", "content": {"node": "sql_agent", "status": "running", "message": "Executing hospital cost query..."}}
   
   ```
4. **Stream Termination Marker:**
   ```
   data: [DONE]
   
   ```

---

## 11. Standardized AG-UI Protocol Bridge

Implemented in `medicare/api/routes/agui.py`. Connects external standardized agent UI frameworks:
- Ingests `AGUIRunRequest` (`messages`, `run_id`, `thread_id`, `user_id`, `properties`).
- Translates execution into `run_started` and `run_completed` lifecycle markers.
- Multiplexes native graph events while stripping internal system prompt initialization details.
- Emits standardized custom status events over SSE.

---

## 12. Streamlit User Interface Specification

Located in `ui/` (`app.py`, `client.py`, `config.py`, `state.py`, `styles.css`, `pages/`, and `components/`).

### 12.1 Multi-Page Architecture (`st.navigation`)
1. **Chat (`ui/pages/chat.py` - Default):**
   - **Persistent Banner:** Slim sample-data disclaimer (`⚠️ Sample data — not medical or insurance advice`).
   - **Empty State:** Welcome banner, 3 capability cards (Hospital Costs, Policies & Coverage, Personal Documents), and dynamic suggestion chips from `/medicare/suggestions`.
   - **Live Stepper (`st.status`):** Visualizes pipeline execution (Guardrail, Supervisor, SQL Agent, Policy RAG, Writer, Verifier) with retry/rewrite badges; auto-collapses upon answer completion.
   - **Streaming Token Render:** Real-time token streaming with cancel/Stop button.
   - **Answer Display (`render_assistant_answer`):** Single canonical render function for live streaming and historical messages loaded from `/history`.
   - **Table & Chart Tabs:** Native `st.dataframe` with humanized currency formatting and CSV download button, paired with responsive Plotly charts.
   - **Sources Row (`st.popover`):** Clickable `[C1]` popover chips showing source file, scope badge (`Curated Policy` vs `My Document`), section, page, score, and verbatim excerpts.
   - **Reasoning Trace Expander:** "How I got this" expander featuring Plan, SQL query attempts, Policy search rewrites, Grounding verification issues, and stage timings bar chart.
   - **Message Actions:** Thumbs up/down feedback, copy answer, and regenerate last response.
2. **My Documents (`ui/pages/documents.py`):**
   - Drag-and-drop uploader accepting allowed extensions from config.
   - Optional insurer and document type metadata selectors.
   - User uploaded documents table with document status badge and delete controls.
   - Background indexing status polling with `@st.fragment` active only while documents are in `processing` status.
   - Read-only table of curated reference insurance policies.
3. **How It Works (`ui/pages/how_it_works.py`):**
   - Plain-language descriptions of autonomous agent responsibilities.
   - Embedded Mermaid diagrams (`graph_parent.mmd`, `graph_sql.mmd`, `graph_policy.mmd`) with source code viewers.
   - Live backend diagnostics: AI execution mode, embedding backend, table row counts, and indexed policy chunk counts.

### 12.2 Shared Sidebar Across All Pages (`ui/components/sidebar.py`)
- App title with live backend health badge (`🟢 Live`, `🟡 Mock`, `🔴 Offline`).
- `➕ New Chat` primary action button that resets session state and starts a fresh thread.
- Previous conversations search and selection list with client-side TTL caching.
- Document scope selector: `Both | Curated | Mine` via `st.segmented_control`.
- My Documents summary badge (e.g. `2 ready, 1 processing`).
- Settings expander with model badge, stream tokens toggle, and show reasoning trace toggle (voice toggle strictly removed).
- Live database row counts and policy vector store chunk metrics.
- Version footer and legal disclaimer.

### 12.3 Session State Helper Keys (`ui/state.py`)
All session state variables are encapsulated in typed getter/setter helper functions without scattered raw keys:
- `user_id`: UUID string (never rendered or displayed in UI).
- `thread_id`: Active thread UUID string.
- `messages`: Active thread chat messages.
- `active_agent`: Target agent key (`medicare-navigator`).
- `active_model`: Selected foundational model.
- `stream_tokens`: SSE token streaming boolean toggle.
- `show_trace`: Reasoning trace display toggle.
- `doc_scope`: Active document retrieval filter (`both`, `curated`, `mine`).
- `last_run_id`: Execution run identifier for feedback submission.
- `is_generating` / `cancel_requested`: Run state management for Stop button and cancellation.

### 12.4 Gateway HTTP & SSE Endpoints Used
The UI communicates exclusively with the backend over HTTP via `MediCareClient`:
- `GET /health`: Infrastructure health probe.
- `GET /app/config`: Dynamic UI labels, features (`features.voice = false`), and layout settings.
- `GET /info`: Registered agents and foundational model defaults.
- `GET /medicare/status`: Live database row counts, policy chunk counts, and mode.
- `GET /medicare/suggestions`: Dynamic question suggestion chips derived from live database values.
- `POST /agents/{agent_id}/runs/stream`: Server-Sent Events (SSE) pipeline stream.
- `GET /threads`: Enumeration of prior conversation sessions.
- `POST /history`: Reconstruction of conversation history.
- `POST /runs/{run_id}/feedback`: User evaluation rating submission.
- `POST /documents`: User document ingestion.
- `GET /documents`: List user and curated documents.
- `GET /documents/{doc_id}`: Poll document ingestion status.
- `DELETE /documents/{doc_id}`: Delete user document.

---

## 13. Automated Verification & Test Suite

The test suite covers configuration, security, persistence, tools, MediCare agents, API endpoints, streaming, protocol bridges, and UI components with **100% pass rate (153 of 153 passed)**.

### 13.1 Running the Test Suite
```bash
# Execute full pytest suite with verbose output
uv run pytest tests/ -v

# Run linter and formatting checks
uv run ruff check .
uv run ruff format --check .
```

### 13.2 Test Files Breakdown
- `tests/medicare/test_agents.py` (5 tests): MediCareNavigator conversational greeting route, multi-agent coordination, safety guardrails, HospitalSQLAgent standalone, PolicyRAGAgent standalone.
- `tests/graph/test_medicare_guardrails.py` (7 tests): SQL injection blocking, medical emergency intercepts, self-harm crisis hotline, and PII redaction.
- `tests/graph/test_medicare_router.py` (4 tests): Intent classification (`policy_only`, `data_only`, `both`, `conversational`) and multi-turn entity carry-over.
- `tests/medicare/test_medicare_sql_agent.py` (3 tests): Self-correcting retry loop, error recovery, and maximum retry exhaustion.
- `tests/tools/test_medicare_sql_tool.py` (8 tests): Read-only SQLite pragmas, destructive DML rejection, stacked query prevention, and row caps.
- `tests/medicare/test_medicare_policy.py` (4 tests): ChromaDB semantic retrieval, BM25 fallback, insurer filtering, and empty index handling.
- `tests/medicare/test_medicare_setup.py` (5 tests): Idempotent SQLite schema migration, CSV data loading with validation, and markdown chunking.
- `tests/medicare/test_medicare_chart.py` (3 tests): Dynamic ChartSpec builder, column detection, and INR currency formatting.
- `tests/e2e/test_medicare_navigator_e2e.py` (6 tests): End-to-end SSE event lifecycle, `/medicare/status` endpoint, and mock retry flows.
- `tests/api/test_api_endpoints.py` (7 tests): Integration tests for `/health`, `/info`, `/medicare-navigator/invoke`, model rejection, and `/feedback`.
- `tests/api/test_streaming.py` (2 tests): SSE streaming protocol against `/medicare-navigator/stream` and `/stream`.
- `tests/api/test_threads_and_history.py` (1 test): History reconstruction and strict cross-user tenant isolation.
- `tests/api/test_agui_bridge.py` (1 test): Standardized AG-UI protocol bridge translation.
- `tests/storage/test_storage.py` (4 tests): SQLite & In-Memory checkpointers, long-term memory store, and thread catalog auto-titling ($\le 60$ chars).
- `tests/security/test_security.py` (4 tests): Bearer auth verification, model allowlist validation, reserved parameter rejection, and prompt injection moderation.
- `tests/medicare/test_config.py` (2 tests): Default settings schema and allowed models validation.
- `tests/tools/test_tools.py` (6 tests): Calculator tool, Web search tool, Weather tool, Vector store tool, Cloud KB tool, and MCP client tool.

---

## 14. Deployment & Containerization

### 14.1 Running Locally
```bash
# Terminal 1: FastAPI Gateway Service
uv run uvicorn medicare.api.app:create_app --factory --host 0.0.0.0 --port 8080 --reload

# Terminal 2: Streamlit Multimodal UI
uv run streamlit run ui/app.py --server.port 8501
```

### 14.2 Seeding Seed Data & Indexing Policies
```bash
# Initialize hospital database and index insurance policies
uv run python -m medicare.medicare.setup --all
```

### 14.3 Docker & Docker Compose
`Dockerfile` provides a lightweight, multi-stage Python 3.11 build. `docker-compose.yml` orchestrates the gateway service and Streamlit web app:

```yaml
version: '3.8'

services:
  medicare-api:
    build:
      context: .
      dockerfile: Dockerfile
    command: uvicorn medicare.api.app:create_app --factory --host 0.0.0.0 --port 8080
    ports:
      - "8080:8080"
    environment:
      - HOST=0.0.0.0
      - PORT=8080
      - STORAGE_ENGINE=sqlite
      - SQLITE_PATH=/app/data/medicare.db
      - USE_MOCK_MODELS=false
      - GROQ_API_KEY=${GROQ_API_KEY}
      - GROQ_MODEL=openai/gpt-oss-120b
    volumes:
      - medicare_var:/app/var
    restart: unless-stopped

  medicare-ui:
    build:
      context: .
      dockerfile: Dockerfile
    command: streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
    ports:
      - "8501:8501"
    environment:
      - BACKEND_SERVICE_URL=http://medicare-api:8080
    depends_on:
      - medicare-api
    restart: unless-stopped

volumes:
  medicare_var:
```

---

## 15. Extension Guide for Autonomous AI Engineers

### 15.1 Adding New Clinical Data Entities
1. **Extend Schema:** Add new tables or columns in `medicare/medicare/schema.py` and update `TABLE_ALLOWLIST` and `COLUMN_ALLOWLIST`.
2. **Update CSV Importer:** Add validation logic in `medicare/medicare/csv_import.py` to ingest new seed CSV records.
3. **Update Prompts:** Update `SQL_SCHEMA_PROMPT` in `medicare/medicare/schema.py` so the model understands the new entity relationships.

### 15.2 Adding New Insurance Policies
1. Drop new policy markdown documents into `data/policies/<insurer_name>/`.
2. Run the policy indexer:
   ```bash
   uv run python -m medicare.medicare.setup --index-policies
   ```
3. The chunker will automatically parse headings, extract clauses, generate metadata, and index vectors in ChromaDB.

### 15.3 Adding New Pipeline Nodes
1. Implement the node function in `medicare/medicare/graph/nodes_parent.py` (or subgraphs):
   ```python
   async def my_custom_node(
       state: NavigatorState, emit: Callable[[str, Any], Any] | None = None
   ) -> NavigatorState:
       # Custom processing logic
       return state
   ```
2. Integrate the node call into the StateGraph assembly in `medicare/medicare/graph/build.py`.
3. Add corresponding verification tests in `tests/medicare/test_agents.py`.
