"""Server-Sent Events (SSE) serialization and streaming event encoders."""

import json

from medicare.domain.models import ChatMessage, TaskTelemetryEvent


def encode_token_event(token: str) -> str:
    """Format token delta SSE chunk."""
    payload = json.dumps({"type": "token", "content": token})
    return f"data: {payload}\n\n"


def encode_message_event(message: ChatMessage) -> str:
    """Format completed message SSE chunk."""
    payload = json.dumps({"type": "message", "content": message.model_dump()})
    return f"data: {payload}\n\n"


def encode_custom_task_event(event: TaskTelemetryEvent) -> str:
    """Format asynchronous custom background task telemetry event."""
    payload = json.dumps(
        {"type": "custom", "channel": "task_status", "content": event.model_dump()}
    )
    return f"data: {payload}\n\n"


def encode_agent_status_event(content: dict) -> str:
    """Format custom agent_status progression event."""
    payload = json.dumps({"type": "custom", "channel": "agent_status", "content": content})
    return f"data: {payload}\n\n"


def encode_interrupt_event(prompt: str, run_id: str) -> str:
    """Format human-in-the-loop interrupt notification event."""
    msg = ChatMessage(type="ai", content=prompt, run_id=run_id)
    payload = json.dumps({"type": "interrupt", "content": msg.model_dump()})
    return f"data: {payload}\n\n"


def encode_error_event(error_text: str) -> str:
    """Format error SSE chunk."""
    payload = json.dumps({"type": "error", "content": error_text})
    return f"data: {payload}\n\n"


def encode_done_marker() -> str:
    """Terminal SSE stream completion marker."""
    return "data: [DONE]\n\n"
