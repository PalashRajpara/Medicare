"""Execution graph engine and event stream orchestrator."""

from datetime import UTC, datetime
from typing import Any

from medicare.domain.models import ChatMessage, CheckpointSnapshot
from medicare.domain.protocols import CheckpointStoreProtocol
from medicare.runtime.context import ExecutionContext


class ExecutionEngine:
    """Coordinates state checkpoints, history accumulation, and thread persistence."""

    def __init__(self, checkpointer: CheckpointStoreProtocol) -> None:
        self.checkpointer = checkpointer

    async def load_history(self, thread_id: str) -> list[ChatMessage]:
        """Load accumulated thread messages from latest checkpoint."""
        return await self.checkpointer.get_thread_history(thread_id)

    async def persist_turn(
        self,
        context: ExecutionContext,
        messages: list[ChatMessage],
        step_index: int,
        scratchpad: dict[str, Any] | None = None,
        interrupted: bool = False,
    ) -> CheckpointSnapshot:
        """Create and save an immutable checkpoint snapshot for the thread."""
        channel_values = {
            "messages": [m.model_dump() for m in messages],
            "scratchpad": scratchpad or {},
            "interrupted": interrupted,
        }
        metadata = {
            "run_id": context.run_id,
            "user_id": context.user_id,
            "agent_id": context.agent_id,
            "model": context.model,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        snapshot = CheckpointSnapshot(
            thread_id=context.thread_id,
            step_index=step_index,
            channel_values=channel_values,
            metadata=metadata,
        )

        await self.checkpointer.save_checkpoint(snapshot)
        return snapshot
