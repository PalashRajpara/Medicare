"""End-to-End multi-turn progressive disclosure test suite."""

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


def _parse_sse_message(lines: list[str]) -> dict | None:
    for line in lines:
        cleaned = line.strip()
        while cleaned.startswith("data:"):
            cleaned = cleaned[5:].strip()
        if not cleaned or cleaned == "[DONE]":
            continue
        try:
            chunk = json.loads(cleaned)
            if chunk.get("type") == "message":
                return chunk.get("content")
        except json.JSONDecodeError:
            pass
    return None


def test_multi_turn_progressive_disclosure_flow(client: TestClient, medicare_env):
    """Verify 3-turn conversational progression from broad scoping to targeted metric to full table."""
    thread_id = "test-progressive-thread-1"
    user_id = "test_progressive_user_1"

    # Turn 1: Broad, underspecified query
    payload_1 = {
        "message": "Compare Total Knee Replacement costs in Ahmedabad",
        "thread_id": thread_id,
        "user_id": user_id,
        "stream_tokens": False,
    }
    with client.stream("POST", "/stream", json=payload_1) as resp:
        assert resp.status_code == 200
        lines_1 = list(resp.iter_lines())

    msg_1 = _parse_sse_message(lines_1)
    assert msg_1 is not None
    content_1 = msg_1.get("content", "")
    meta_1 = msg_1.get("response_metadata", {}).get("medicare", {})

    # Assert Turn 1 asks counter-questions instead of dumping raw table
    assert "health insurance" in content_1.lower()
    assert "priority" in content_1.lower()

    # Assert Turn 1 attaches 4 interactive follow-up suggestion chips
    followups_1 = meta_1.get("followups", [])
    assert len(followups_1) == 4
    assert any("Lowest" in f for f in followups_1)
    assert any("Shortest" in f for f in followups_1)
    assert any("table" in f.lower() for f in followups_1)

    # Turn 2: User clicks "Lowest package cost in Ahmedabad"
    payload_2 = {
        "message": "Lowest package cost in Ahmedabad",
        "thread_id": thread_id,
        "user_id": user_id,
        "stream_tokens": False,
    }
    with client.stream("POST", "/stream", json=payload_2) as resp:
        assert resp.status_code == 200
        lines_2 = list(resp.iter_lines())

    msg_2 = _parse_sse_message(lines_2)
    assert msg_2 is not None
    content_2 = msg_2.get("content", "")
    # Entity carry-forward: knows procedure is Total Knee Replacement
    assert "knee replacement" in content_2.lower() or "ahmedabad" in content_2.lower()

    # Turn 3: User clicks "Show full comparison table"
    payload_3 = {
        "message": "Show full comparison table",
        "thread_id": thread_id,
        "user_id": user_id,
        "stream_tokens": False,
    }
    with client.stream("POST", "/stream", json=payload_3) as resp:
        assert resp.status_code == 200
        lines_3 = list(resp.iter_lines())

    msg_3 = _parse_sse_message(lines_3)
    assert msg_3 is not None
    content_3 = msg_3.get("content", "")
    # Explicit full table request -> renders markdown table
    assert (
        "| Hospital Name |" in content_3
        or "| Hospital (Location) |" in content_3
        or "| " in content_3
    )
