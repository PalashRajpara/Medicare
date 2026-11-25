"""End-to-End integration tests for MediCare & Claim Navigator AI."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from medicare.config import settings
from medicare.medicare.dataset.csv_import import import_all_csvs
from medicare.medicare.dataset.policy_indexer import index_markdown_policies
from medicare.medicare.dataset.schema import ALL_DDL_STATEMENTS


@pytest.fixture
def medicare_env(tmp_path, monkeypatch):
    """Set up temporary isolated SQLite and ChromaDB directories for E2E testing."""
    db_file = str(tmp_path / "hospitals.db")
    chroma_dir = str(tmp_path / "chroma")

    manifest_db = str(tmp_path / "manifest.db")

    monkeypatch.setattr(settings, "MEDICARE_DB_PATH", db_file)
    monkeypatch.setattr(settings, "CHROMA_PATH", chroma_dir)
    monkeypatch.setattr(settings, "MANIFEST_DB_PATH", manifest_db)
    monkeypatch.setattr(settings, "CHROMA_COLLECTION", "test_medicare")
    monkeypatch.setattr(settings, "USE_MOCK_MODELS", True)
    monkeypatch.setattr(settings, "DEFAULT_AGENT", "medicare-navigator")

    from medicare.rag.store import reset_chroma_store

    reset_chroma_store()

    conn = sqlite3.connect(db_file)
    for stmt in ALL_DDL_STATEMENTS:
        conn.cursor().executescript(stmt)
    conn.commit()
    conn.close()

    import_all_csvs(seed_dir="tests/fixtures/medicare/seed", db_path=db_file)
    index_markdown_policies(
        policy_dir="tests/fixtures/medicare/policies",
        chroma_path=chroma_dir,
        collection_name="test_medicare",
    )

    return db_file, chroma_dir


def test_medicare_status_endpoint(client: TestClient, medicare_env):
    """Verify GET /medicare/status returns correct table counts and index metrics."""
    resp = client.get("/medicare/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["db_exists"] is True
    assert data["tables"]["hospitals"] == 3
    assert data["tables"]["hospital_procedures"] == 10
    assert data["tables"]["insurer_acceptance"] == 6
    assert data["policy_chunks"] > 0
    assert data["mode"] == "mock"
    assert data["chroma"] in ("ok", "fallback")


def _parse_sse_lines(lines: list[str]) -> tuple[list[dict], dict | None]:
    """Extract agent_status custom events and final message from SSE lines."""
    status_events = []
    final_message = None

    for line in lines:
        cleaned = line.strip()
        while cleaned.startswith("data:"):
            cleaned = cleaned[5:].strip()
        if not cleaned or cleaned == "[DONE]":
            continue
        try:
            chunk = json.loads(cleaned)
            if chunk.get("type") == "custom" and chunk.get("channel") == "agent_status":
                status_events.append(chunk.get("content"))
            elif chunk.get("type") == "message":
                final_message = chunk.get("content")
        except json.JSONDecodeError:
            pass

    return status_events, final_message


def test_stream_e2e_event_progression_and_metadata(client: TestClient, medicare_env):
    """Verify /stream emits agent_status events in order, then tokens, then message with metadata, then [DONE]."""
    payload = {
        "message": "Compare knee replacement costs across hospitals in Ahmedabad and check Star Health cashless",
        "thread_id": "test-e2e-stream-1",
        "stream_tokens": True,
    }

    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    assert any("[DONE]" in line for line in lines)

    status_events, final_message = _parse_sse_lines(lines)

    # Verify agent_status events in order
    nodes_called = [e.get("node") for e in status_events]
    assert "guardrail" in nodes_called
    assert "router" in nodes_called
    assert "policy_rag" in nodes_called
    assert "sql" in nodes_called
    assert "synthesizer" in nodes_called

    # Verify structured medicare metadata payload
    assert final_message is not None
    meta = final_message.get("response_metadata", {}).get("medicare", {})
    assert meta.get("route") == "both"
    assert "citations" in meta
    assert "sql_trace" in meta
    assert "table" in meta
    assert "chart" in meta
    assert "disclaimers" in meta
    assert meta.get("guardrail", {}).get("blocked") is False


def test_history_endpoint_returns_medicare_metadata(client: TestClient, medicare_env):
    """Verify /history preserves and returns the rich medicare metadata from checkpoint."""
    thread_id = "test-history-thread-1"
    payload = {
        "message": "Compare knee replacement in Ahmedabad",
        "thread_id": thread_id,
        "stream_tokens": False,
    }

    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())

    hist_resp = client.post("/history", json={"thread_id": thread_id})
    assert hist_resp.status_code == 200
    messages = hist_resp.json()["messages"]
    assert len(messages) >= 2
    ai_msg = messages[-1]
    assert ai_msg["type"] == "ai"
    assert "medicare" in ai_msg["response_metadata"]


def test_empty_database_returns_friendly_message_no_500(client: TestClient, tmp_path, monkeypatch):
    """Verify missing database returns HTTP 200 with guidance and no 500 error."""
    missing_db = str(tmp_path / "does_not_exist.db")
    monkeypatch.setattr(settings, "MEDICARE_DB_PATH", missing_db)
    monkeypatch.setattr(settings, "USE_MOCK_MODELS", True)

    payload = {
        "message": "Compare cardiac surgery costs in Mumbai",
        "thread_id": "test-empty-db-thread",
        "stream_tokens": False,
    }

    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    _, final_msg = _parse_sse_lines(lines)
    message_content = final_msg.get("content", "") if final_msg else ""

    assert (
        "not loaded yet" in message_content.lower()
        or "python -m medicare.medicare.setup" in message_content
    )


def test_guardrail_blocking_in_stream(client: TestClient, medicare_env):
    """Verify that a blocked prompt emits a blocked status event and safe message with no downstream execution."""
    payload = {
        "message": "I feel hopeless and want to end my life",
        "thread_id": "test-harm-stream",
        "stream_tokens": False,
    }

    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    status_events, final_message = _parse_sse_lines(lines)

    # Only 1 guardrail status event with status="blocked"
    assert len(status_events) == 1
    assert status_events[0]["node"] == "guardrail"
    assert status_events[0]["status"] == "blocked"
    assert status_events[0]["category"] == "self_harm"

    # Message contains helpline
    assert final_message is not None
    assert "14416" in final_message["content"]


def test_demo_fail_first_retry_flow(client: TestClient, medicare_env, monkeypatch):
    """With MEDICARE_DEMO_FAIL_FIRST=True, verify retry SSE event is emitted and final query succeeds."""
    from medicare.providers.router import router

    router.mock_engine.reset_demo_state()
    monkeypatch.setattr(settings, "MEDICARE_DEMO_FAIL_FIRST", True)

    payload = {
        "message": "Compare knee replacement in Ahmedabad",
        "thread_id": "test-fail-first-demo",
        "stream_tokens": False,
    }

    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())

    status_events, _ = _parse_sse_lines(lines)
    retry_events = [e for e in status_events if e.get("status") == "retry"]

    assert len(retry_events) >= 1
    assert retry_events[0]["retry"] == 1
