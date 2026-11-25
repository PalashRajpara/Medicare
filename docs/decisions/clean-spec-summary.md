# Specification Summary: Clean Architecture & Multi-Agent Platform

This document captures the core functional and architectural design principles of the platform.

## 1. Core Platform Principles
- **Stateless Gateway with Persistent Checkpointing**: HTTP and SSE endpoints maintain no ephemeral in-memory state; state is committed via thread-scoped checkpointer transactions.
- **Dual Streaming Semantics**: Support concurrent token deltas (`type: "token"`) and structured task lifecycle events (`type: "message"`, `type: "custom"`, `type: "status"`).
- **Dual-Tier State Model**:
  - *Short-Term Checkpointing*: Thread-scoped snapshots capturing execution steps and tool invocations.
  - *Long-Term Memory*: User-scoped namespace-isolated key-value stores for persistent user attributes.
- **Human-in-the-Loop Interruption**: Execution graphs support pausing for confirmation or missing input with state preserved in checkpoints.
- **Clinical & Security Moderation**: Dedicated pre-execution guardrails inspecting for prompt injection, medical emergency triage, crisis intervention, and PII masking.
