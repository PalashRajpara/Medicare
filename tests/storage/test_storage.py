"""Persistence layer tests for Checkpointers and Long-Term Memory."""

import pytest

from medicare.domain.models import ChatMessage, CheckpointSnapshot
from medicare.storage.checkpointer import InMemoryCheckpointer, SqliteCheckpointer
from medicare.storage.memory_store import InMemoryMemoryStore
from medicare.storage.thread_catalog import generate_thread_title


@pytest.mark.asyncio
async def test_in_memory_checkpointer():
    cp = InMemoryCheckpointer()
    thread_id = "test-th-1"

    msg1 = ChatMessage(type="human", content="Calculate compound interest")
    msg2 = ChatMessage(type="ai", content="Sure, here is the formula...")

    snap = CheckpointSnapshot(
        thread_id=thread_id,
        step_index=1,
        channel_values={"messages": [msg1.model_dump(), msg2.model_dump()]},
        metadata={"user_id": "user-a", "agent_id": "medicare-navigator"},
    )

    await cp.save_checkpoint(snap)

    # Check latest
    latest = await cp.get_latest_checkpoint(thread_id)
    assert latest is not None
    assert latest.step_index == 1

    # Check history
    history = await cp.get_thread_history(thread_id)
    assert len(history) == 2
    assert history[0].type == "human"

    # Check list threads
    threads = await cp.list_threads(user_id="user-a")
    assert len(threads) == 1
    assert threads[0].thread_id == thread_id
    assert "Calculate compound interest" in threads[0].title


@pytest.mark.asyncio
async def test_sqlite_checkpointer(tmp_path):
    db_file = str(tmp_path / "test_checkpoints.db")
    cp = SqliteCheckpointer(db_path=db_file)
    await cp.initialize()

    thread_id = "th-sqlite-99"
    msg1 = ChatMessage(type="human", content="What is the weather in Paris?")
    snap = CheckpointSnapshot(
        thread_id=thread_id,
        step_index=0,
        channel_values={"messages": [msg1.model_dump()]},
        metadata={"user_id": "user-b", "agent_id": "hospital-sql"},
    )
    await cp.save_checkpoint(snap)

    history = await cp.get_thread_history(thread_id)
    assert len(history) == 1
    assert history[0].content == "What is the weather in Paris?"

    threads = await cp.list_threads(user_id="user-b")
    assert len(threads) == 1
    assert threads[0].title == "What is the weather in Paris?"


@pytest.mark.asyncio
async def test_memory_store():
    store = InMemoryMemoryStore()
    ns = ("user-123",)

    # Get empty
    assert await store.get(ns, "birthdate") is None

    # Put
    await store.put(ns, "birthdate", {"value": "1994-08-15"})
    retrieved = await store.get(ns, "birthdate")
    assert retrieved is not None
    assert retrieved["value"] == "1994-08-15"

    # Delete
    deleted = await store.delete(ns, "birthdate")
    assert deleted is True
    assert await store.get(ns, "birthdate") is None


def test_thread_catalog_helpers():
    title = generate_thread_title(
        "This is a very long question asking about complex distributed systems and database checkpointer snapshots that should be truncated to 60 characters",
        max_length=60,
    )
    assert len(title) <= 63  # with '...'
    assert title.endswith("...")
