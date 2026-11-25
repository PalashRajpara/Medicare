"""Thread-scoped checkpoint persistence engines."""

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from medicare.domain.models import (
    ChatMessage,
    CheckpointSnapshot,
    ConversationThread,
)
from medicare.domain.protocols import CheckpointStoreProtocol


class InMemoryCheckpointer(CheckpointStoreProtocol):
    """Fast in-memory checkpointer for testing and ephemeral workloads."""

    def __init__(self) -> None:
        self._checkpoints: list[CheckpointSnapshot] = []
        self._threads: dict[str, ConversationThread] = {}

    async def save_checkpoint(self, checkpoint: CheckpointSnapshot) -> None:
        self._checkpoints.append(checkpoint)

        # Update thread catalog
        thread_id = checkpoint.thread_id
        user_id = checkpoint.metadata.get("user_id")
        agent_id = checkpoint.metadata.get("agent_id", "default")
        now = datetime.now(UTC)

        # Auto title from first human message if thread is new
        title = "New Conversation"
        messages = checkpoint.channel_values.get("messages", [])
        for m in messages:
            content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            role = m.get("type", "") if isinstance(m, dict) else getattr(m, "type", "")
            if role == "human" and content:
                title = content.strip().replace("\n", " ")[:60]
                break

        if thread_id in self._threads:
            th = self._threads[thread_id]
            th.updated_at = now
            if user_id and not th.user_id:
                th.user_id = user_id
        else:
            self._threads[thread_id] = ConversationThread(
                thread_id=thread_id,
                user_id=user_id,
                agent_id=agent_id,
                created_at=now,
                updated_at=now,
                title=title,
            )

    async def get_latest_checkpoint(self, thread_id: str) -> CheckpointSnapshot | None:
        matched = [c for c in self._checkpoints if c.thread_id == thread_id]
        if not matched:
            return None
        return max(matched, key=lambda c: c.step_index)

    async def get_thread_history(self, thread_id: str) -> list[ChatMessage]:
        latest = await self.get_latest_checkpoint(thread_id)
        if not latest:
            return []
        raw_msgs = latest.channel_values.get("messages", [])
        result: list[ChatMessage] = []
        for m in raw_msgs:
            if isinstance(m, ChatMessage):
                result.append(m)
            elif isinstance(m, dict):
                result.append(ChatMessage(**m))
        return result

    async def list_threads(
        self, user_id: str, agent_id: str | None = None, limit: int = 20
    ) -> list[ConversationThread]:
        threads = [
            t
            for t in self._threads.values()
            if t.user_id == user_id and (agent_id is None or t.agent_id == agent_id)
        ]
        threads.sort(key=lambda t: t.updated_at, reverse=True)
        return threads[:limit]


class SqliteCheckpointer(CheckpointStoreProtocol):
    """Persistent SQLite checkpointer supporting async database operations."""

    def __init__(self, db_path: str = "var/platform.db") -> None:
        self.db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables and indexes if they do not exist."""
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    channel_values TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_checkpoints_thread 
                ON checkpoints(thread_id, step_index DESC)
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    agent_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_threads_user 
                ON threads(user_id, updated_at DESC)
                """
            )
            await db.commit()
        self._initialized = True

    async def save_checkpoint(self, checkpoint: CheckpointSnapshot) -> None:
        await self.initialize()
        now_str = datetime.now(UTC).isoformat()
        user_id = checkpoint.metadata.get("user_id")
        agent_id = checkpoint.metadata.get("agent_id", "default")

        # Derive auto title
        title = "New Conversation"
        messages = checkpoint.channel_values.get("messages", [])
        for m in messages:
            content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            role = m.get("type", "") if isinstance(m, dict) else getattr(m, "type", "")
            if role == "human" and content:
                title = content.strip().replace("\n", " ")[:60]
                break

        # Serialize channel values
        channel_data: dict[str, Any] = {}
        for k, v in checkpoint.channel_values.items():
            if k == "messages" and isinstance(v, list):
                channel_data[k] = [
                    item.model_dump() if hasattr(item, "model_dump") else item for item in v
                ]
            else:
                channel_data[k] = v

        channel_json = json.dumps(channel_data)
        meta_json = json.dumps(checkpoint.metadata)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO checkpoints (checkpoint_id, thread_id, step_index, channel_values, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.thread_id,
                    checkpoint.step_index,
                    channel_json,
                    meta_json,
                    now_str,
                ),
            )
            # Upsert thread catalog
            cursor = await db.execute(
                "SELECT thread_id, title FROM threads WHERE thread_id = ?",
                (checkpoint.thread_id,),
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    "UPDATE threads SET updated_at = ?, user_id = COALESCE(?, user_id) WHERE thread_id = ?",
                    (now_str, user_id, checkpoint.thread_id),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO threads (thread_id, user_id, agent_id, created_at, updated_at, title)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (checkpoint.thread_id, user_id, agent_id, now_str, now_str, title),
                )
            await db.commit()

    async def get_latest_checkpoint(self, thread_id: str) -> CheckpointSnapshot | None:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT checkpoint_id, thread_id, step_index, channel_values, metadata, created_at
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY step_index DESC
                LIMIT 1
                """,
                (thread_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return CheckpointSnapshot(
                checkpoint_id=row[0],
                thread_id=row[1],
                step_index=row[2],
                channel_values=json.loads(row[3]),
                metadata=json.loads(row[4]),
                created_at=datetime.fromisoformat(row[5]),
            )

    async def get_thread_history(self, thread_id: str) -> list[ChatMessage]:
        latest = await self.get_latest_checkpoint(thread_id)
        if not latest:
            return []
        raw_msgs = latest.channel_values.get("messages", [])
        return [ChatMessage(**m) if isinstance(m, dict) else m for m in raw_msgs]

    async def list_threads(
        self, user_id: str, agent_id: str | None = None, limit: int = 20
    ) -> list[ConversationThread]:
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            if agent_id:
                query = """
                    SELECT thread_id, user_id, agent_id, created_at, updated_at, title
                    FROM threads
                    WHERE user_id = ? AND agent_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """
                params = (user_id, agent_id, limit)
            else:
                query = """
                    SELECT thread_id, user_id, agent_id, created_at, updated_at, title
                    FROM threads
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """
                params = (user_id, limit)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [
                ConversationThread(
                    thread_id=r[0],
                    user_id=r[1],
                    agent_id=r[2],
                    created_at=datetime.fromisoformat(r[3]),
                    updated_at=datetime.fromisoformat(r[4]),
                    title=r[5],
                )
                for r in rows
            ]
