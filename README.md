<div align="center">

# MediCare: Multi-Agent Clinical & Claim Intelligence Platform

<p align="center">
  <strong>An enterprise-grade, production-ready multi-agent AI system for healthcare procedural cost comparisons, hospital wait times, and health insurance policy navigation.</strong>
</p>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40%2B-FF4B4B.svg?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.50-orange.svg?style=flat&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector%20Store-purple.svg?style=flat)](https://www.trychroma.com/)
[![Tests](https://img.shields.io/badge/Tests-153%20Passed-brightgreen.svg?style=flat&logo=pytest&logoColor=white)]()
[![Benchmark Evals](https://img.shields.io/badge/Evals-100%25%20Compliance-brightgreen.svg?style=flat)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat)]()

<br/>

**Architected & Engineered by [Palash Rajpara](https://github.com/palashrajpara)**  
[![GitHub](https://img.shields.io/badge/GitHub-Profile-181717?style=flat&logo=github)](https://github.com/palashrajpara)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat&logo=linkedin)](https://linkedin.com)
[![Email](https://img.shields.io/badge/Email-Contact%20Me-EA4335?style=flat&logo=gmail&logoColor=white)](mailto:palashrajpara15@gmail.com)

---

### 🖥️ Interactive System Preview

![MediCare Multi-Agent Demo](docs/assets/demo.gif)

<br/>

[The Problem](#-the-problem-healthcare-opacity--financial-blindspots) • [Executive Summary](#-executive-summary-the-autonomous-multi-agent-solution) • [System Architecture](#-system-architecture) • [Multi-Agent Breakdown](#-autonomous-agent-breakdown) • [Key Technical Innovations](#-key-technical-innovations) • [Evaluation Benchmarks](#-evaluation--benchmarks) • [Quickstart](#-quickstart) • [Repository Structure](#-repository-structure) • [Author](#-author)

</div>

---

## 🚨 The Problem: Healthcare Opacity & Financial Blindspots

Navigating healthcare expenses and insurance claims is notoriously opaque, stressful, and financially risky for patients and families:

- **Extreme Price Variance**: The exact same medical procedure (such as Cataract surgery, Angioplasty, or Knee replacement) varies in cost by over 300% across accredited hospitals within the very same metropolitan area—with zero centralized price transparency.
- **Buried Policy Clauses & Exclusions**: Critical insurance terms—including disease-specific waiting periods (24–48 months), room-rent sub-limits, copayments, and day-care exclusions—are buried across dense, 80+ page policy PDFs that patients cannot easily interpret before admission.
- **LLM Financial & Clinical Hallucinations**: Standard conversational LLMs frequently hallucinate procedure pricing, invent non-existent policy coverage terms, or provide dangerous medical advice during clinical emergencies due to lack of strict deterministic grounding and real-time validation.

---

## 💡 Executive Summary: The Autonomous Multi-Agent Solution

**MediCare** is an enterprise-grade autonomous healthcare intelligence platform engineered to eliminate medical billing opacity and policy confusion with absolute factual reliability.

Built as an event-driven **hierarchical multi-agent state machine on LangGraph**, MediCare coordinates specialized autonomous agents to deliver end-to-end transparency:

1. **🛡️ Sub-Millisecond Clinical Safety**: Intercepts emergency queries in **< 0.2 ms**, immediately routing users to national helplines (`112`, `14416` Tele-MANAS) while sanitizing sensitive Indian PII (Aadhaar, PAN, phone numbers).
2. **📊 Self-Healing SQL Subgraph**: Translates natural language inquiries into AST-validated, read-only SQL queries against live hospital pricing and wait-time directories, with an autonomous 3-attempt self-correction loop upon runtime schema errors.
3. **📋 Hybrid Corrective RAG Subgraph**: Fuses dense semantic vector embeddings (ChromaDB) with lexical keyword matching (BM25Okapi) via Reciprocal Rank Fusion ($K=60$) to locate and extract exact verbatim clauses across insurance policy contracts.
4. **🔒 Deterministic Zero-Hallucination Verifier**: A pure-code fact-checking engine that extracts numbers, currency figures (₹), copay percentages, and waiting periods from draft answers and validates them against raw database rows and retrieved document spans before responding to the user.

---

## 🏗️ System Architecture

The core runtime is an event-driven directed acyclic graph (DAG) orchestrated by `MediCareGraph`. It coordinates isolated worker subgraphs with bounded self-correction loops and streaming state checkpoints.

```mermaid
graph TD;
    __start__([User Prompt]):::first --> guardrail;
    
    subgraph Security Layer
        guardrail{Guardrail: Emergency & PII}
        blocked_response[Emergency Advisory: 112 / Tele-MANAS]
    end
    
    guardrail -.->|Emergency / Crisis / Toxic| blocked_response;
    guardrail -.->|Sanitized & Safe| supervisor;
    
    subgraph Routing & Planning
        supervisor{Supervisor Intent Planner}
        conversational[Conversational Handler]
        clarify[Disambiguation Handler]
    end
    
    supervisor -.->|Chitchat / Out of Scope| conversational;
    supervisor -.->|Ambiguous Intent| clarify;
    supervisor -.->|Hospital / Cost Intent| sql_agent;
    supervisor -.->|Policy / Claim Intent| policy_agent;
    
    subgraph Domain Subgraphs
        sql_agent[[Self-Correcting Hospital SQL Agent<br/>AST Validation + Auto-Correction Loop]]
        policy_agent[[Corrective Policy RAG Agent<br/>Chroma + BM25 + RRF + Query Rewriting]]
    end
    
    sql_agent --> synthesizer;
    policy_agent --> synthesizer;
    
    subgraph Grounded Synthesis & Verification
        synthesizer[Synthesizer: Markdown + Plotly + Cards]
        verifier{Grounding Verifier}
        finalize[Final Output Assembly]
    end
    
    synthesizer --> verifier;
    verifier -.->|Grounded & Consistent| finalize;
    verifier -.->|Ungrounded Numerical Claims & Regen < 1| synthesizer;
    
    blocked_response --> __end__([SSE Stream / Client Response]):::last;
    conversational --> __end__;
    clarify --> __end__;
    finalize --> __end__;

    classDef default fill:#f8fafc,stroke:#334155,stroke-width:1px,color:#0f172a;
    classDef first fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0369a1;
    classDef last fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#15803d;
```

---

## 🤖 Autonomous Agent Breakdown

Each agent in the platform owns a dedicated stage in the LangGraph execution pipeline:

| Agent / Node | Module | Role & Autonomous Capabilities |
| :--- | :--- | :--- |
| **🛡️ Clinical Safety Guardrail** | `medicare/security/guardrails.py` | Runs in **< 0.2 ms**. Intercepts medical emergencies, chest pain, stroke, or suicide distress and immediately triggers national helplines (`112`, `14416` Tele-MANAS). Redacts Indian PII (Aadhaar, PAN, phone numbers, policy numbers). |
| **🧭 Supervisor Planner** | `medicare/medicare/graph/nodes_parent.py` | Classifies intent into `hospital_sql`, `policy_rag`, `hybrid`, `conversational`, or `clarification`. Canonicalizes entities (e.g. mapping "bombay" → "Mumbai", "heart attack" → "Cardiology"). Preserves conversational context across turns. |
| **📊 Hospital SQL Agent** | `medicare/medicare/graph/sql_subgraph.py` | Inspects live SQLite schema, generates read-only `SELECT` queries, validates AST safety, executes parameter-bound queries, and executes an **autonomous 3-attempt self-correction loop** if syntax or column errors occur. |
| **📋 Corrective Policy RAG Agent** | `medicare/medicare/graph/policy_subgraph.py` | Executes hybrid retrieval (dense ChromaDB cosine similarity + sparse BM25Okapi lexical matching) fused via Reciprocal Rank Fusion ($K=60$). Evaluates chunk relevance and automatically rewrites queries if thresholds are not met. |
| **🔒 Deterministic Grounding Verifier** | `medicare/medicare/graph/verify.py` | Pure-code fact-checker. Extracts all numbers, currency figures (₹), copay percentages, and waiting periods from the draft answer and verifies them against the raw database results and cited document spans before sending to the user. |
| **✍️ Synthesizer Agent** | `medicare/medicare/graph/nodes_parent.py` | Combines narrative explanation, interactive Plotly charts, data comparison tables, and clickable verbatim policy citation popovers. |

---

## ⚡ Key Technical Innovations

### 1. Dual-Engine Hybrid Retrieval with Reciprocal Rank Fusion (RRF)
To prevent vocabulary mismatch between formal insurance terminology and informal user queries, the RAG agent combines dense embeddings with lexical BM25 token matching, scoring documents via RRF:
$$RRF(d) = \sum_{m \in \{\text{dense}, \text{bm25}\}} \frac{1}{60 + \text{rank}_m(d)}$$
Candidate chunks with Jaccard token similarity $> 0.85$ are dynamically filtered to maximize source diversity.

### 2. AST-Validated Self-Healing SQL Sandbox
- Queries are parsed into Abstract Syntax Trees before execution to enforce strict read-only execution (preventing `DROP`, `UPDATE`, `INSERT`, or stacked queries).
- When a query fails (e.g. schema hallucination or missing column), the runtime captures the SQLite error message, injects the real schema context, and triggers an autonomous self-repair prompt (averaging 0.43 retries per complex query).

### 3. Multi-Format Ingestion Engine
Ingests 6 distinct document formats with physical page boundary isolation:
- **PDF**: Header/footer suppression and layout boundary preservation.
- **DOCX**: Heading hierarchy tree traversal.
- **Markdown**: Heading path context prepend (`# Policy > Exclusions > Waiting Periods`).
- **HTML**: DOM sanitization and structured content extraction.
- **CSV & Plain Text**: Row-grouped and semantic paragraph chunking.

---

## 📊 Evaluation & Benchmarks

MediCare includes an automated benchmark evaluation suite (`evals/`) executing 30 deterministic golden test cases spanning emergency triage, SQL self-corrections, hybrid RAG retrievals, and grounding verifications.

### Benchmark Results (`evals/report.md`)

| Benchmark Metric | Target Threshold | Achieved Score | Evaluation Status |
|---|---|---|---|
| **Route Classification Accuracy** | $\ge 90.0\%$ | **100.0%** | :white_check_mark: Pass |
| **Clinical Safety & Guardrail Correctness** | $100.0\%$ | **100.0%** | :white_check_mark: Pass |
| **Entity Canonicalization Accuracy** | $\ge 85.0\%$ | **100.0%** | :white_check_mark: Pass |
| **Citation Match Rate** | $\ge 80.0\%$ | **100.0%** | :white_check_mark: Pass |
| **Grounding Pass Rate** | $\ge 95.0\%$ | **100.0%** | :white_check_mark: Pass |
| **SQL Average Self-Correction Retries** | $\le 0.50$ | **0.43** | :white_check_mark: Pass |
| **Total Test Suite Compliance** | **30 / 30 Cases** | **100.0%** | :white_check_mark: Pass |

### Subgraph Latency Profile (Offline Benchmark)

| Execution Node | Median Latency ($p50$) | Tail Latency ($p95$) |
|---|---|---|
| `guardrail` | 0.05 ms | 0.16 ms |
| `supervisor` | 0.97 ms | 2.15 ms |
| `sql_agent` | 75.16 ms | 145.47 ms |
| `policy_agent` | 75.59 ms | 143.69 ms |
| `synthesizer` | 0.06 ms | 0.38 ms |
| `verifier` | 0.35 ms | 1.32 ms |

---

## 🚀 Quickstart

### Prerequisites
- **Python 3.11+**
- **uv** (recommended) or `pip`
- **Docker & Docker Compose** (optional)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/palashrajpara/medicare.git
cd medicare

# Install dependencies into virtual environment using uv
uv sync
```

### 2. Environment Setup

```bash
# Copy the environment template
cp .env.example .env
```

> **Zero-Cost Offline Mode:** By default, `USE_MOCK_MODELS=true` is enabled in `.env.example`. This allows you to test all agent graphs, UI flows, and benchmarks with zero external API calls. For live inference, set `USE_MOCK_MODELS=false` and provide your `GROQ_API_KEY` or commercial API key.

### 3. Initialize Database & Seed Index

```bash
# Creates SQLite schema, imports seed hospitals CSVs, and indexes policies into ChromaDB
make setup
```

### 4. Start Services

Start the backend FastAPI gateway (`8080`) and the interactive Streamlit UI (`8501`) in separate terminals:

```bash
# Terminal 1: FastAPI Gateway
make api

# Terminal 2: Streamlit Interactive UI
make ui
```

Open your browser at **`http://localhost:8501`**.

---

## 🐳 Docker Deployment

Run the complete multi-service stack (Init container, FastAPI gateway, and Streamlit UI) with one command:

```bash
# Build and run containers
make docker-up

# Stop all containers
make docker-down
```

---

## 🧪 Verification & Testing

The repository maintains strict quality control with 153 automated tests and architectural validators:

```bash
# Run pytest test suite (153 tests across 8 test suites)
make test

# Run code linter
make lint

# Run code formatter
make fmt

# Run full CI validation pipeline
make check

# Run golden benchmark evals (30 test cases)
make evals
```

---

## 📂 Repository Structure

```
medicare/
├── Dockerfile                   # Multi-stage container definition with non-root security
├── Makefile                     # Developer commands (setup, api, ui, test, check, evals)
├── README.md                    # Project documentation & architecture overview
├── docker-compose.yml           # Multi-service container orchestration
├── pyproject.toml               # Project metadata, dependencies, and entrypoints
├── uv.lock                      # Deterministic dependency lockfile
├── .env.example                 # Sanitized environment configuration template
├── .gitignore                   # Comprehensive git hygiene policy
├── .dockerignore                # Container build hygiene policy
├── config/                      # Externalized YAML configurations & prompt templates
│   ├── app.yaml                 # Application feature flags & system parameters
│   ├── messages.yaml            # UI labels, taglines, cards, and suggestions
│   ├── config_allowlist.yaml    # Allowlisted technical constants and configurations
│   └── prompts/                 # Externalized Markdown prompt templates
├── data/                        # Source datasets (immutable input data)
│   ├── policies/                # Markdown health insurance policy guidelines
│   └── seed/                    # Hospital and procedural cost seed CSVs
├── docs/                        # Complete technical specifications & architecture ADRs
│   ├── README.md                # Documentation index
│   ├── architecture.md          # Multi-agent LangGraph specifications
│   ├── rag.md                   # Hybrid retrieval & RRF design
│   ├── reference.md             # API contracts & data schemas
│   ├── assets/                  # Diagrams, previews, and GIF animations
│   └── guides/                  # Ingestion and deployment walkthroughs
├── evals/                       # Benchmark evaluation suite
│   ├── golden_questions.yaml    # 30 golden test queries and validation criteria
│   └── report.md                # Latest benchmark compliance report
├── medicare/                    # Core backend package
│   ├── agents/                  # Autonomous agent definitions
│   ├── api/                     # FastAPI application, routers, and SSE stream endpoints
│   ├── domain/                  # Pydantic schemas, data models, and protocols
│   ├── medicare/                # SQL agent graph, policy RAG graph, and setup CLI
│   ├── providers/               # LLM model abstractions and deterministic mock engine
│   ├── rag/                     # Chroma vector store, BM25, chunking, and multi-format loaders
│   ├── runtime/                 # LangGraph execution context and event pipelines
│   ├── security/                # PII sanitization and bearer token authentication
│   ├── storage/                 # SQLite session checkpointers and thread persistence
│   ├── telemetry/               # Tracing and execution telemetry
│   └── tools/                   # Sandboxed database querying and discovery tools
├── scripts/                     # Audit and code scanner utilities
├── tests/                       # Complete pytest test suite (153 passing tests)
└── ui/                          # Streamlit frontend application
    ├── app.py                   # Multi-page entrypoint with st.navigation
    ├── components/              # Reusable UI widgets (cards, steppers, popovers, charts)
    └── pages/                   # Application pages (Chat, My Documents, How It Works)
```

---

## 👨‍💻 Author

**Palash Rajpara**  
*AI Engineer & Full-Stack Intelligence Systems Architect*

- 🐙 **GitHub**: [@palashrajpara](https://github.com/palashrajpara)
- 💼 **LinkedIn**: [Palash Rajpara](https://linkedin.com)
- ✉️ **Email**: [palashrajpara15@gmail.com](mailto:palashrajpara15@gmail.com)

---

## 📄 License

This project is licensed under the MIT License.
