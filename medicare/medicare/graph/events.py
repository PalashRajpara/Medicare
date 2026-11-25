"""Stream writer event emission helpers for LangGraph custom SSE streams."""

from typing import Any

from langgraph.types import StreamWriter


def emit_status(
    writer: StreamWriter | None,
    node: str,
    status: str,
    message: str,
    retry: int | None = None,
    max_retries: int | None = None,
    category: str | None = None,
    **kwargs: Any,
) -> None:
    """Emit structured node lifecycle status over LangGraph custom stream mode."""
    if writer is None:
        return
    payload: dict[str, Any] = {
        "kind": "status",
        "node": node,
        "status": status,
        "message": message,
    }
    if retry is not None:
        payload["retry"] = retry
    if max_retries is not None:
        payload["max_retries"] = max_retries
    if category is not None:
        payload["category"] = category
    for k, v in kwargs.items():
        if v is not None:
            payload[k] = v
    writer(payload)


def emit_token(writer: StreamWriter | None, text: str) -> None:
    """Emit typewriter token delta over LangGraph custom stream mode."""
    if writer is None:
        return
    writer({"kind": "token", "text": text})
