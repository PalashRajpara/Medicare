"""State models, entities, and helpers for MediCare & Claim Navigator."""

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from medicare.config_loader import get_app_config
from medicare.domain.models import (
    ChartSpec,
    Citation,
    SQLAttempt,
    SupervisorPlan,
    TableResult,
)


def format_inr(amount: int | float | None) -> str:
    """Format integer or float using currency symbol configured in config/app.yaml."""
    sym = get_app_config().get("currency_symbol", "")
    if amount is None:
        return f"{sym}0"

    try:
        val = int(round(float(amount)))
    except (ValueError, TypeError):
        return f"{sym}{amount}"

    if val < 0:
        return f"-{format_inr(-val)}"

    s = str(val)
    if len(s) <= 3:
        return f"{sym}{s}"

    # Last 3 digits
    last3 = s[-3:]
    remaining = s[:-3]

    # Group remaining digits in sets of 2 from right to left
    parts = []
    while len(remaining) > 2:
        parts.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        parts.insert(0, remaining)

    return f"{sym}{','.join(parts)},{last3}"


def merge_dicts(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    """Reducer helper to merge two timing/metric dictionaries."""
    res = dict(a or {})
    if b:
        res.update(b)
    return res


class SQLAgentResult(BaseModel):
    """Aggregated output from SQL Agent worker sub-graph."""

    attempts: list[SQLAttempt] = Field(default_factory=list)
    table: TableResult | None = None
    success: bool = False
    broadened: bool = False
    error_summary: str | None = None
    empty_db: bool = False
    final_sql: str | None = None


class PolicyAgentResult(BaseModel):
    """Aggregated output from Policy Agent RAG worker sub-graph."""

    citations: list[Citation] = Field(default_factory=list)
    rewrites_used: int = 0
    insurer_fallback: bool = False
    no_evidence: bool = False
    index_empty: bool = False


class GuardrailOutcome(BaseModel):
    """Result of clinical pre-execution safety guardrail checks."""

    blocked: bool = False
    category: str | None = None
    safe_message: str | None = None
    redacted_question: str = ""
    soft_flags: list[str] = Field(default_factory=list)


class GroundingReport(BaseModel):
    """Verification results evaluating final answer against evidence."""

    passed: bool = True
    issues: list[str] = Field(default_factory=list)
    regenerated: bool = False
    fallback_used: bool = False


class TraceEntry(BaseModel):
    """Discrete trace entry for graph execution timeline."""

    node: str
    status: str
    ms: float = 0.0
    note: str | None = None


class NavigatorState(TypedDict, total=False):
    """LangGraph execution state container for MediCare Navigator."""

    # Input
    question: str
    history: list[dict[str, Any]]
    user_id: str
    thread_id: str
    run_id: str
    doc_scope: Literal["curated", "mine", "both"]

    # Guardrail
    guardrail: GuardrailOutcome

    # Supervisor
    plan: SupervisorPlan

    # Workers
    sql_result: SQLAgentResult | None
    policy_result: PolicyAgentResult | None

    # Output
    answer: str
    chart: ChartSpec | None
    grounding: GroundingReport | None
    regenerations: int
    followups: list[str]

    # Observability
    trace: Annotated[list[TraceEntry], operator.add]
    timings: Annotated[dict[str, float], merge_dicts]
    llm_calls: Annotated[int, operator.add]


class LegacyNavigatorState(BaseModel):
    """Legacy compatibility state model for transitional or test code."""

    question: str
    user_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None

    is_safe: bool = True
    blocked_category: str | None = None
    safety_message: str | None = None
    is_medical_emergency: bool = False
    needs_medical_advice_disclaimer: bool = False

    route: Literal["conversational", "policy_only", "data_only", "both", "clarify"] = "both"
    extracted_entities: dict[str, str] = Field(default_factory=dict)

    citations: list[Citation] = Field(default_factory=list)
    policy_summary: str | None = None
    policy_index_empty: bool = False

    sql_attempts: list[SQLAttempt] = Field(default_factory=list)
    final_sql: str | None = None
    table: TableResult | None = None
    sql_success: bool = False
    database_empty: bool = False

    answer_markdown: str = ""
    chart: ChartSpec | None = None
    disclaimers: list[str] = Field(default_factory=list)
