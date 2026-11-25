"""Base class and common contract for all MediCare topologies."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from medicare.domain.models import ChatMessage
from medicare.domain.protocols import CheckpointStoreProtocol, MemoryStoreProtocol
from medicare.runtime.context import ExecutionContext


class BaseAgent(ABC):
    """Abstract base class for all catalog agents."""

    key: str
    description: str

    @abstractmethod
    async def invoke(
        self,
        context: ExecutionContext,
        message: str,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """Execute a synchronous conversational turn."""
        ...

    @abstractmethod
    async def stream(
        self,
        context: ExecutionContext,
        message: str,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
        stream_tokens: bool = True,
        agent_config: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Execute a streaming turn yielding SSE protocol strings."""
        ...
