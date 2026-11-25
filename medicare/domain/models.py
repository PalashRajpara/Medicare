"""Domain models and API contracts for MediCare."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def generate_uuid() -> str:
    """Generate standard UUID string."""
    return str(uuid.uuid4())


class ToolCallDescriptor(BaseModel):
    """Descriptor for assistant tool invocation requests."""

    id: str = Field(default_factory=generate_uuid)
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """Unified chat message representation across layers."""

    type: Literal["human", "ai", "tool", "custom"]
    content: str
    tool_calls: list[ToolCallDescriptor] = Field(default_factory=list)
    tool_call_id: str | None = None
    run_id: str | None = None
    response_metadata: dict[str, Any] = Field(default_factory=dict)
    custom_data: dict[str, Any] = Field(default_factory=dict)


class ConversationThread(BaseModel):
    """Metadata record for a conversation session."""

    thread_id: str
    user_id: str | None = None
    agent_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    title: str = "New Conversation"


class CheckpointSnapshot(BaseModel):
    """State snapshot captured at an execution node boundary."""

    checkpoint_id: str = Field(default_factory=generate_uuid)
    thread_id: str
    step_index: int = 0
    channel_values: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TaskTelemetryEvent(BaseModel):
    """Structured telemetry event for asynchronous operations."""

    task_id: str
    task_name: str
    state: Literal["new", "running", "complete"]
    result: Literal["success", "error"] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class RunFeedbackRecord(BaseModel):
    """Human evaluation feedback record."""

    run_id: str
    key: str = "human-feedback-stars"
    score: float = Field(ge=0.0, le=1.0)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


# ==============================================================================
# API Request & Response Contracts
# ==============================================================================


class InvokeRequest(BaseModel):
    """Request payload for synchronous and streaming agent invocations."""

    message: str
    model: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    doc_scope: Literal["curated", "mine", "both"] = "both"
    agent_config: dict[str, Any] | None = None


class StreamRequest(InvokeRequest):
    """Request payload for real-time SSE streaming invocations."""

    stream_tokens: bool = True


class HistoryRequest(BaseModel):
    """Request payload for retrieving conversation message history."""

    thread_id: str


class HistoryResponse(BaseModel):
    """Response payload containing reconstructed thread messages."""

    messages: list[ChatMessage]


class ThreadListResponse(BaseModel):
    """Response payload containing enumerated user threads."""

    threads: list[ConversationThread]


class FeedbackRequest(BaseModel):
    """Request payload for submitting run evaluation feedback."""

    run_id: str
    key: str = "human-feedback-stars"
    score: float = Field(ge=0.0, le=1.0)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    """Response payload for successful feedback submission."""

    status: str = "success"


class AgentInfo(BaseModel):
    """Agent description descriptor."""

    key: str
    description: str


class InfoResponse(BaseModel):
    """Metadata discovery response."""

    agents: list[AgentInfo]
    models: list[str]
    default_agent: str
    default_model: str


class HealthResponse(BaseModel):
    """Service health probe response."""

    status: str
    telemetry: str


class AppConfigResponse(BaseModel):
    """Application UI labels, layout configuration, features, and settings."""

    model_config = {"extra": "allow"}

    app_name: str = ""
    app_title: str = ""
    app_subtitle: str = ""
    domain_description: str = ""
    currency_symbol: str = ""
    currency_code: str = "INR"
    currency_locale: str = "en_IN"
    features: dict[str, Any] = Field(default_factory=lambda: {"voice": False})
    empty_state: dict[str, Any] = Field(default_factory=dict)
    ui: dict[str, Any] = Field(default_factory=dict)
    sample_questions: list[str] = Field(default_factory=list)


class AGUIRunRequest(BaseModel):
    """Standardized AG-UI execution input."""

    messages: list[dict[str, Any]]
    run_id: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# Domain Data & Agent Artifact Contracts
# ==============================================================================


class SQLAttempt(BaseModel):
    """Details of a single SQL query execution attempt."""

    attempt: int
    sql: str
    error: str | None = None
    kind: str | None = None  # syntax | no_such_table | no_such_column | forbidden | timeout | other
    row_count: int | None = None


class Citation(BaseModel):
    """Insurance policy clause citation."""

    source: str
    section: str
    text: str
    score: float = 0.0
    doc_id: str | None = None
    page: int | None = None
    scope: Literal["curated", "user"] = "curated"
    cite_id: str | None = None  # e.g. "C1", "C2" marker in answer text
    doc_type: str | None = None
    insurer: str | None = None


class TableResult(BaseModel):
    """Structured tabular result from SQL execution."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False


class ChartSpec(BaseModel):
    """Specification for plotting charts in UI without Streamlit dependencies."""

    chart_type: str = "grouped_bar"
    title: str = ""
    x_axis: str = ""
    y_axis: str = ""
    secondary_y_axis: str | None = None
    color_by: str | None = None
    error_min: str | None = None
    error_max: str | None = None
    data: list[dict[str, Any]] = Field(default_factory=list)


class SupervisorPlan(BaseModel):
    """Plan generated by the supervisor agent."""

    route: Literal["conversational", "data_only", "policy_only", "both", "clarify"] = "both"
    entities: dict[str, Any] = Field(default_factory=dict)
    rewritten_question: str = ""
    doc_scope: Literal["curated", "mine", "both"] = "both"
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: float = 1.0
    rationale: str = ""
