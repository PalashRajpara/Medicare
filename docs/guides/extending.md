# Extending MediCare

This guide outlines patterns for extending agents, tools, graphs, and models.

## Architectural Layering Rules

When modifying or extending the repository, you must respect the layer boundaries:
- `medicare/api/` imports from `agents/`, `security/`, `storage/`, `domain/`.
- `medicare/agents/` may import `medicare/`, `rag/`, `tools/`, `providers/`, `runtime/`.
- `medicare/rag/`, `tools/`, `providers/`, `security/`, `runtime/`, `storage/`, `domain/` must **not** import from `agents/`, `api/`, or `medicare/`.
- `ui/` must **not** import from `medicare/` at all (it communicates with the backend exclusively via HTTP).

## Adding New Tools

1. Subclass `BaseTool` in `medicare/tools/base.py`.
2. Implement synchronous `run()` and asynchronous `arun()`.
3. Register the tool in your agent or LangGraph dependencies container (`Dependencies`).

## Modifying Graph Workflows

Compiled LangGraph workflows reside under `medicare/medicare/graph/`:
- `build.py`: Main StateGraph assembly and compilation.
- `nodes_parent.py`: Supervisor routing, guardrail verification, and response synthesis.
- `sql_subgraph.py` & `nodes_sql.py`: Self-correcting SQL execution loop.
- `policy_subgraph.py` & `nodes_policy.py`: Corrective RAG retrieval and grading.
- `state.py`: TypedDict state definitions.

Export updated graphs using:
```bash
python scripts/export_graph.py
```
