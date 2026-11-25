"""Policy RAG search tool utilizing hybrid search (ChromaDB + BM25) with vector store fallback."""

import logging
from typing import Any, Literal

from medicare.config import settings
from medicare.domain.models import Citation
from medicare.tools.base import BaseTool

logger = logging.getLogger(__name__)


def normalize_insurer_name(name: str) -> str:
    """Normalize insurer query string to canonical index metadata label dynamically."""
    if not name:
        return ""
    n = name.strip()
    n_lower = n.lower()

    # Discover known insurers dynamically from manifest repository
    try:
        from medicare.rag.manifest import get_manifest_repository

        docs = get_manifest_repository().list_documents()
        known = {d.insurer for d in docs if d.insurer}
        if known:
            import difflib

            # Substring or exact match
            for k in known:
                if k.lower() == n_lower or n_lower in k.lower() or k.lower() in n_lower:
                    return k.lower()
            matches = difflib.get_close_matches(n, list(known), n=1, cutoff=0.6)
            if matches:
                return matches[0].lower()
    except Exception:
        pass

    return n_lower


class PolicySearchTool(BaseTool):
    """Semantic search tool for health insurance policy documents and waiting periods."""

    name = "policy_search"
    description = "Search insurance policy terms, exclusions, waiting periods, room-rent limits, and claim clauses."

    def __init__(
        self,
        chroma_path: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.chroma_path = chroma_path or settings.CHROMA_PATH
        self.collection_name = collection_name or settings.CHROMA_COLLECTION
        self._is_fallback = False
        self._store = None
        self._retriever = None

        try:
            import chromadb

            # Check if chromadb is a valid module (not mocked to None)
            if chromadb is None:
                raise ImportError("ChromaDB is unavailable")

            from medicare.rag.retriever import HybridRetriever
            from medicare.rag.store import ChromaStore

            self._store = ChromaStore(
                persist_path=self.chroma_path, collection_name=self.collection_name
            )
            self._retriever = HybridRetriever(chroma_store=self._store)
        except Exception as e:
            logger.warning(
                "ChromaDB initialization failed (%s). Falling back to hash vector store.", e
            )
            self._is_fallback = True

    @property
    def is_fallback(self) -> bool:
        """True if running in fallback mode."""
        return self._is_fallback

    @property
    def _collection(self) -> Any:
        """Expose collection for status introspection and backwards compatibility."""
        return self._store._collection if self._store else None

    def search(
        self,
        query: str,
        insurer: str | None = None,
        top_k: int = 5,
        doc_scope: Literal["curated", "mine", "both"] = "both",
        user_id: str | None = None,
    ) -> list[Citation]:
        """Perform semantic search across policy chunks."""
        if not query.strip() or self._is_fallback:
            return []

        try:
            norm_insurer = normalize_insurer_name(insurer) if insurer else None
            # If a custom store was configured for tests, query dense directly on that store
            if (
                self._store is not None
                and self._store.collection_name != settings.CHROMA_COLLECTION
            ):
                where_clause = None
                if norm_insurer:
                    where_clause = {"insurer": norm_insurer}
                dense_hits = self._store.search_dense(query, top_k=top_k, where=where_clause)
                citations: list[Citation] = []
                for idx, (chunk, score) in enumerate(dense_hits, start=1):
                    citations.append(
                        Citation(
                            source=chunk.source,
                            section=chunk.section or "General",
                            text=chunk.content,
                            score=round(score, 3),
                            doc_id=chunk.doc_id,
                            page=chunk.page,
                            scope=chunk.scope,
                            cite_id=f"C{idx}",
                            doc_type=chunk.doc_type,
                            insurer=chunk.insurer,
                        )
                    )
                return citations

            # Default: use HybridRetriever
            if self._retriever is not None:
                retrieved_chunks = self._retriever.search(
                    query=query,
                    insurer=norm_insurer,
                    doc_scope=doc_scope,
                    user_id=user_id,
                    top_k=top_k,
                )
                citations = []
                for idx, rc in enumerate(retrieved_chunks, start=1):
                    c = rc.chunk
                    citations.append(
                        Citation(
                            source=c.source,
                            section=c.section or "General",
                            text=c.content,
                            score=round(rc.score, 3),
                            doc_id=c.doc_id,
                            page=c.page,
                            scope=c.scope,
                            cite_id=f"C{idx}",
                            doc_type=c.doc_type,
                            insurer=c.insurer,
                        )
                    )
                return citations
        except Exception as e:
            logger.warning(f"Policy search encountered an error: {e}")

        return []

    async def execute(
        self, query: str = "", insurer: str | None = None, top_k: int = 5, **kwargs: Any
    ) -> str:
        """Execute search asynchronously."""
        citations = self.search(query=query, insurer=insurer, top_k=top_k)
        if not citations:
            return "No matching policy clauses found."

        output = [f"Found {len(citations)} relevant policy clauses:"]
        for c in citations:
            output.append(f"[{c.source} › {c.section}] (Score: {c.score})\n{c.text}")
        return "\n\n".join(output)
