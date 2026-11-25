"""Long-term hierarchical user memory store."""

from typing import Any

from medicare.domain.protocols import MemoryStoreProtocol


class InMemoryMemoryStore(MemoryStoreProtocol):
    """In-memory implementation of user-scoped long-term memory."""

    def __init__(self) -> None:
        self._store: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}

    async def get(self, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
        return self._store.get((namespace, key))

    async def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        self._store[(namespace, key)] = value

    async def delete(self, namespace: tuple[str, ...], key: str) -> bool:
        if (namespace, key) in self._store:
            del self._store[(namespace, key)]
            return True
        return False
