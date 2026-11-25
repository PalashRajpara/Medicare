"""Protocol interfaces for MediCare components."""

from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable

from medicare.domain.models import (
    ChatMessage,
    CheckpointSnapshot,
    ConversationThread,
)


@runtime_checkable
class CheckpointStoreProtocol(Protocol):
    """Interface for thread-scoped checkpoint persistence."""

    async def save_checkpoint(self, checkpoint: CheckpointSnapshot) -> None:
        """Persist a new checkpoint snapshot."""
        ...

    async def get_latest_checkpoint(self, thread_id: str) -> CheckpointSnapshot | None:
        """Retrieve the most recent checkpoint for a given thread."""
        ...

    async def get_thread_history(self, thread_id: str) -> list[ChatMessage]:
        """Reconstruct the ordered list of messages for a thread."""
        ...

    async def list_threads(
        self, user_id: str, agent_id: str | None = None, limit: int = 20
    ) -> list[ConversationThread]:
        """List threads owned by user_id, optionally filtered by agent_id."""
        ...


@runtime_checkable
class MemoryStoreProtocol(Protocol):
    """Interface for cross-session hierarchical long-term memory."""

    async def get(self, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
        """Retrieve a stored attribute dictionary."""
        ...

    async def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        """Store or update an attribute dictionary."""
        ...

    async def delete(self, namespace: tuple[str, ...], key: str) -> bool:
        """Delete an attribute by key."""
        ...


@runtime_checkable
class ModelProviderProtocol(Protocol):
    """Interface for foundational model generation."""

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> ChatMessage:
        """Generate a complete assistant response turn."""
        ...

    async def stream_tokens(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream token deltas for typewriter display."""
        ...

    async def chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate response turn with structured tool calls {content, tool_calls}."""
        ...
