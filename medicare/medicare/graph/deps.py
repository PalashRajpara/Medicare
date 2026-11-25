"""Dependency injection container for MediCare LangGraph nodes and sub-graphs."""

from dataclasses import dataclass

from medicare.config import Settings, settings
from medicare.domain.protocols import (
    CheckpointStoreProtocol,
    MemoryStoreProtocol,
    ModelProviderProtocol,
)
from medicare.providers.router import router
from medicare.rag.retriever import HybridRetriever
from medicare.storage.checkpointer import InMemoryCheckpointer
from medicare.storage.memory_store import InMemoryMemoryStore
from medicare.tools.policy_search import PolicySearchTool
from medicare.tools.sql_query import SQLiteQueryTool


@dataclass
class Dependencies:
    """Collaborator dependencies injected into graph nodes."""

    settings: Settings
    provider: ModelProviderProtocol
    sql_tool: SQLiteQueryTool
    policy_tool: PolicySearchTool
    retriever: HybridRetriever
    memory_store: MemoryStoreProtocol
    checkpointer: CheckpointStoreProtocol

    @classmethod
    def default(cls) -> "Dependencies":
        return cls(
            settings=settings,
            provider=router,
            sql_tool=SQLiteQueryTool(),
            policy_tool=PolicySearchTool(),
            retriever=HybridRetriever(),
            memory_store=InMemoryMemoryStore(),
            checkpointer=InMemoryCheckpointer(),
        )
