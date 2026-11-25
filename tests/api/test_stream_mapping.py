"""Tests for Server-Sent Events (SSE) stream event ordering and metadata contracts."""

import json

import pytest
from fastapi.testclient import TestClient

from medicare.api.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_sse_event_progression_order_and_terminal_marker(client: TestClient):
    """Verify stream delivers agent_status events first, tokens, message event, then [DONE]."""
    payload = {
        "message": "Compare cataract surgery costs in Ahmedabad",
        "thread_id": "test-stream-order",
        "stream_tokens": True,
    }

    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        raw_lines = list(resp.iter_lines())

    event_sequence = []
    for line in raw_lines:
        cleaned = line.strip()
        while cleaned.startswith("data:"):
            cleaned = cleaned[5:].strip()
        if cleaned == "[DONE]":
            event_sequence.append("[DONE]")
            continue
        if not cleaned:
            continue
        try:
            chunk = json.loads(cleaned)
            ev_type = chunk.get("type")
            channel = chunk.get("channel")
            if ev_type == "custom" and channel == "agent_status":
                event_sequence.append("status")
            elif ev_type == "token":
                event_sequence.append("token")
            elif ev_type == "message":
                event_sequence.append("message")
        except json.JSONDecodeError:
            pass

    assert "status" in event_sequence
    assert "message" in event_sequence
    assert event_sequence[-1] == "[DONE]"

    # Ensure all statuses appear before message
    first_msg_idx = event_sequence.index("message")
    for idx, ev in enumerate(event_sequence):
        if ev == "status":
            assert idx < first_msg_idx, "Status event appeared after final message event"
