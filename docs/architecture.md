# MediCare & Claim Navigator Architecture

This document describes the LangGraph multi-agent architecture, compiled StateGraph topologies, bounded worker sub-graphs, and Server-Sent Events (SSE) streaming lifecycle of MediCare & Claim Navigator AI.

---

## 1. Top-Level Parent Graph (`MediCareGraph`)

The parent graph coordinates security guardrails, supervisor intent planning, parallel worker fan-out, response synthesis, and grounding verification.

```mermaid
graph TD;
	__start__([start]):::first
	guardrail(guardrail)
	blocked_response(blocked_response)
	supervisor(supervisor)
	conversational(conversational)
	clarify(clarify)
	sql_agent(sql_agent)
	policy_agent(policy_agent)
	synthesizer(synthesizer)
	verifier(verifier)
	finalize(finalize)
	__end__([end]):::last

	__start__ --> guardrail;
	guardrail -.->|Blocked| blocked_response;
	guardrail -.->|Safe| supervisor;
	supervisor -.->|Conversational| conversational;
	supervisor -.->|Ambiguous| clarify;
	supervisor -.->|data_only / both| sql_agent;
	supervisor -.->|policy_only / both| policy_agent;
	sql_agent --> synthesizer;
	policy_agent --> synthesizer;
	synthesizer --> verifier;
	verifier -.->|Passed / Fallback Used| finalize;
	verifier -.->|Ungrounded & Regen < 1| synthesizer;
	blocked_response --> __end__;
	clarify --> __end__;
	conversational --> __end__;
	finalize --> __end__;

	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

### Parent Graph Execution Nodes:
1. **`guardrail`**: Evaluates pre-execution clinical emergencies, crisis/self-harm patterns, prompt injection threats, and redacts Indian PII (phone, Aadhaar, PAN, emails, claim IDs).
2. **`blocked_response`**: Emits safe, structured emergency advisory (Tele-MANAS `14416`, Emergency `112`) and terminates stream without worker invocations.
3. **`supervisor`**: Evaluates intent (`data_only`, `policy_only`, `both`, `conversational`, `clarify`), extracts & canonicalizes entities (`city`, `procedure`, `insurer`) via `difflib`, and manages conversational carry-over across turns.
4. **`conversational`**: Generates friendly greeting and capability explanation without invoking tool workers.
5. **`clarify`**: Proactively requests clarification for fundamentally ambiguous inquiries (e.g. underspecified comparison requests).
6. **`sql_agent`**: Invokes the Hospital SQL Agent sub-graph in parallel.
7. **`policy_agent`**: Invokes the Policy RAG Agent sub-graph in parallel.
8. **`synthesizer`**: Compiles evidence from SQL and Policy workers into a grounded 4-part structured markdown response and Vega-Lite chart spec.
9. **`verifier`**: Pure function validating numeric claims against table/citations, checking citation markers `[C1]`..`[Cn]`, and triggering 1 repair regeneration or deterministic fallback.
10. **`finalize`**: Emits terminal completion telemetry.

---

## 2. Hospital SQL Sub-Graph (`SQLAgentGraph`)

The SQL worker runs a bounded cyclic sub-graph (`medicare/medicare/graph/sql_subgraph.py`):

```mermaid
graph TD;
	__start__([start]):::first
	load_schema(load_schema)
	generate_sql(generate_sql)
	static_check(static_check)
	execute_sql(execute_sql)
	fix_sql(fix_sql)
	broaden_query(broaden_query)
	finish(finish)
	give_up(give_up)
	__end__([end]):::last

	__start__ --> load_schema;
	load_schema --> generate_sql;
	generate_sql --> static_check;
	static_check -.->|Valid SELECT| execute_sql;
	static_check -.->|Static Rule Violation & Attempts < 4| fix_sql;
	static_check -.->|Attempts >= 4| give_up;
	execute_sql -.->|Success & Rows > 0| finish;
	execute_sql -.->|Success & 0 Rows & Not Broadened| broaden_query;
	execute_sql -.->|Execution Error & Attempts < 4| fix_sql;
	execute_sql -.->|Attempts >= 4| give_up;
	broaden_query --> static_check;
	fix_sql -.->|Fixed Query| static_check;
	fix_sql -.->|Attempts >= 4| give_up;
	finish --> __end__;
	give_up --> __end__;

	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

### Self-Correction & Safety Features:
- **`static_check`**: Pre-execution AST/regex validation ensuring queries are strictly read-only `SELECT`, rejecting DDL/DML, stacked statements (`;`), `sqlite_master` access, and enforcing a `LIMIT 50` row cap.
- **Repeated SQL Detection**: Flags identical queries across attempts to avoid infinite error loops.
- **Dynamic Broadening**: When a valid query returns 0 rows (e.g. strict procedure match), re-executes query with `LIKE '%partial%'` to maximize recall.
- **Bounded Attempts**: Exactly 1 initial query + up to 3 self-correction retries.

---

## 3. Policy RAG Sub-Graph (`PolicyAgentGraph`)

The policy worker runs a corrective RAG sub-graph (`medicare/medicare/graph/policy_subgraph.py`):

```mermaid
graph TD;
	__start__([start]):::first
	plan_query(plan_query)
	retrieve(retrieve)
	grade_chunks(grade_chunks)
	rewrite_query(rewrite_query)
	build_citations(build_citations)
	no_evidence(no_evidence)
	__end__([end]):::last

	__start__ --> plan_query;
	plan_query --> retrieve;
	retrieve --> grade_chunks;
	grade_chunks -.->|Relevant >= 1| build_citations;
	grade_chunks -.->|0 Relevant & Rewrites < 2| rewrite_query;
	grade_chunks -.->|0 Relevant & Rewrites >= 2| no_evidence;
	rewrite_query --> retrieve;
	build_citations --> __end__;
	no_evidence --> __end__;

	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

### Features:
- **Hybrid Dense + Sparse Search**: Combines ChromaDB cosine similarity with `BM25Okapi` sparse retrieval using Reciprocal Rank Fusion (RRF $K=60$).
- **Chunk Grading**: Filters out chunks lacking domain relevance and drops indirect prompt injections.
- **Query Rewriting**: Reformulates query terminology on retrieval misses (up to 2 rewrites).
- **Citation Extraction**: Generates structured citations with 1-based `[C1]`..`[Cn]` reference tags.

---

## 4. Server-Sent Events (SSE) Streaming Sequence

MediCare maintains full backward-compatibility with frontend SSE streaming contracts:

```mermaid
sequenceDiagram
    autonumber
    actor Client as User / Streamlit UI
    participant Agent as MediCare Navigator (LangGraph)
    participant Parent as StateGraph Runner
    participant SQL as SQLAgentGraph
    participant Policy as PolicyAgentGraph
    participant Storage as SQLite Checkpointer

    Client->>Agent: POST /stream (message, thread_id, model)
    Agent->>Parent: astream(input_state)
    Parent-->>Client: SSE custom(channel="agent_status", node="guardrail", status="done")
    Parent-->>Client: SSE custom(channel="agent_status", node="router", status="done")

    par Parallel Execution Fan-Out
        Parent->>SQL: astream(sub_input)
        SQL-->>Client: SSE custom(channel="agent_status", node="sql", status="running")
        opt SQL Retry
            SQL-->>Client: SSE custom(channel="agent_status", node="sql", status="retry", retry=1, max_retries=3)
        end
        SQL-->>Parent: TableResult
        SQL-->>Client: SSE custom(channel="agent_status", node="sql", status="done")
    and
        Parent->>Policy: astream(sub_input)
        Policy-->>Client: SSE custom(channel="agent_status", node="policy_rag", status="running")
        opt Query Rewrite
            Policy-->>Client: SSE custom(channel="agent_status", node="policy_rag", status="rewrite", rewrite=1)
        end
        Policy-->>Parent: Citations
        Policy-->>Client: SSE custom(channel="agent_status", node="policy_rag", status="done")
    end

    Parent-->>Client: SSE custom(channel="agent_status", node="synthesizer", status="running")
    loop Token Streaming
        Parent-->>Client: SSE token("word ")
    end
    Parent-->>Client: SSE custom(channel="agent_status", node="synthesizer", status="done")
    Parent-->>Client: SSE custom(channel="agent_status", node="verifier", status="done")

    Parent->>Storage: Persist checkpoint with response_metadata.medicare
    Parent-->>Client: SSE message(content, response_metadata={medicare: ...})
    Parent-->>Client: SSE [DONE]
```

---

## 5. Frontend UI Architecture (`ui/`)

The Streamlit UI is built with native Streamlit 1.67+ components following a decoupled, HTTP-only client-server pattern:

```mermaid
flowchart TD
    subgraph Streamlit_UI ["Streamlit Frontend (ui/)"]
        Router["app.py (st.navigation router)"]
        Sidebar["components/sidebar.py (Shared Sidebar)"]
        ChatPage["pages/chat.py (Chat Page)"]
        DocsPage["pages/documents.py (My Documents Page)"]
        InfoPage["pages/how_it_works.py (Architecture Page)"]
        AnswerRender["components/answer.py (Unified Renderer)"]
        HTTPClient["client.py (MediCareClient)"]
    end

    subgraph FastAPI_Backend ["FastAPI Gateway (medicare/api/)"]
        ConfigRoute["GET /app/config"]
        StatusRoute["GET /medicare/status"]
        SuggestRoute["GET /medicare/suggestions"]
        StreamRoute["POST /agents/{agent_id}/runs/stream"]
        HistoryRoute["POST /history"]
        ThreadsRoute["GET /threads"]
        FeedbackRoute["POST /runs/{run_id}/feedback"]
        DocsRoute["POST/GET/DELETE /documents"]
    end

    Router --> Sidebar
    Router --> ChatPage
    Router --> DocsPage
    Router --> InfoPage
    ChatPage --> AnswerRender
    Sidebar --> HTTPClient
    ChatPage --> HTTPClient
    DocsPage --> HTTPClient
    InfoPage --> HTTPClient

    HTTPClient -->|Config & Labels| ConfigRoute
    HTTPClient -->|Live Counts| StatusRoute
    HTTPClient -->|Dynamic Chips| SuggestRoute
    HTTPClient -->|SSE Event Stream| StreamRoute
    HTTPClient -->|Thread History| HistoryRoute
    HTTPClient -->|Previous Chats| ThreadsRoute
    HTTPClient -->|Human Evaluation| FeedbackRoute
    HTTPClient -->|Document Ingest & Polling| DocsRoute
```

### UI Architectural Invariants:
1. **HTTP Only**: The UI has zero imports from the backend `medicare` package.
2. **Zero Hardcoded Data**: All domain entities, labels, titles, and capability cards are injected via `GET /app/config` and `config/app.yaml`.
3. **Identical Message Rendering**: Both live streams and historical conversation thread messages render through the exact same function (`render_assistant_answer`).
4. **Isolated Fragment Polling**: `@st.fragment` manages live status polling for background document indexing and sidebar status without triggering full page reruns.
5. **No Voice Prototype Code**: Voice audio features are explicitly excluded (`features.voice = false`), ensuring clean production focus on tabular, procedural, and policy intelligence.
