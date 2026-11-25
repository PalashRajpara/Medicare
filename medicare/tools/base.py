"""Base class and descriptor for MediCare tools."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class for all operational tools."""

    name: str
    description: str

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given arguments and return a string result."""
        ...

    def to_schema(self) -> dict[str, Any]:
        """Return tool descriptor schema for LLM function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
            },
        }
