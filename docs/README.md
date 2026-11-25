# MediCare Documentation Index

Welcome to the MediCare documentation. This directory provides detailed specifications, architecture diagrams, operational guides, and decision records.

## Core Documentation

- [architecture.md](architecture.md): System architecture, LangGraph supervisor topology, and worker execution flow.
- [rag.md](rag.md): Hybrid dense-sparse retrieval, reciprocal rank fusion (RRF), and corrective chunk grading.
- [reference.md](reference.md): Comprehensive system reference, API schemas, configuration defaults, and deployment manifest.

## Visual Graph Diagrams

- [graphs/graph_parent.mmd](graphs/graph_parent.mmd): Mermaid sequence and state graph for the parent supervisor workflow.
- [graphs/graph_sql.mmd](graphs/graph_sql.mmd): Mermaid state diagram for the self-correcting SQL sub-graph.
- [graphs/graph_policy.mmd](graphs/graph_policy.mmd): Mermaid state diagram for the corrective policy RAG sub-graph.

## Operational & Developer Guides

- [guides/running-locally.md](guides/running-locally.md): Step-by-step setup, running API and UI locally, testing, and evals.
- [guides/docker.md](guides/docker.md): Docker Compose multi-container deployment, volume mounts, and health probes.
- [guides/adding-documents.md](guides/adding-documents.md): Managing seed CSV datasets, policy Markdown files, and user uploads.
- [guides/extending.md](guides/extending.md): Guidelines for adding new tools, custom graph nodes, and adhering to layering boundaries.

## Architecture Decision Records (ADRs)

- [decisions/repo-layout.md](decisions/repo-layout.md): Repository restructuring, strict layer decoupling, and runtime state isolation in `var/`.
- [decisions/langgraph-migration.md](decisions/langgraph-migration.md): Migration from legacy sequential loop to compiled LangGraph multi-agent architecture.
- [decisions/dynamic-decisions.md](decisions/dynamic-decisions.md): Elimination of hardcoded schemas, dynamic catalog introspection, and generic database tools.
- [decisions/medicare-decisions.md](decisions/medicare-decisions.md): Clinical safety guardrails, claim terminology, and grounding verifier thresholds.
- [decisions/clean-spec-summary.md](decisions/clean-spec-summary.md): Summary of architectural baseline and refactoring principles.
- [decisions/implementation-plan-summary.md](decisions/implementation-plan-summary.md): Execution stages and verification checkpoints.
- [decisions/hardcode-audit.md](decisions/hardcode-audit.md): Automated hardcoding audit findings and allowlist justifications.
