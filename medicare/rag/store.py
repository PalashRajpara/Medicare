"""ChromaDB persistent vector store for dense retrieval."""

import logging
import os
from typing import Any

import chromadb

from medicare.config import settings
from medicare.rag.embeddings import get_embedding_backend
from medicare.rag.models import ChunkRecord

logger = logging.getLogger(__name__)


class ChromaStore:
    """Manages document chunk embeddings and vector similarity queries in ChromaDB."""

    def __init__(
        self,
        persist_path: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        self.persist_path = persist_path or settings.CHROMA_PATH
        self.collection_name = collection_name or settings.CHROMA_COLLECTION
        os.makedirs(self.persist_path, exist_ok=True)

        self._client = chromadb.PersistentClient(path=self.persist_path)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "MediCare Insurance Policies and User Documents"},
        )
        self._embedder = get_embedding_backend()

    def upsert_chunks(self, chunks: list[ChunkRecord]) -> None:
        """Embed and upsert chunks into Chroma collection."""
        if not chunks:
            return

        ids = [c.chunk_id for c in chunks]
        texts = [c.content for c in chunks]
        embeddings = self._embedder.embed_documents(texts)
        metadatas = [
            {
                "doc_id": c.doc_id,
                "source": c.source,
                "title": c.title,
                "insurer": c.insurer or "",
                "doc_type": c.doc_type,
                "page": c.page if c.page is not None else 0,
                "section": c.section,
                "chunk_index": c.chunk_index,
                "scope": c.scope,
                "user_id": c.user_id or "",
                "content_sha256": c.content_sha256,
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

    def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all chunks associated with a specific doc_id."""
        try:
            self._collection.delete(where={"doc_id": doc_id})
        except Exception as e:
            logger.warning(f"Failed to delete chunks for doc_id {doc_id}: {e}")

    def search_dense(
        self,
        query: str,
        top_k: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Perform dense vector similarity search returning (ChunkRecord, score)."""
        if self._collection.count() == 0:
            return []

        query_vec = self._embedder.embed_query(query)
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_vec],
            "n_results": min(top_k, max(1, self._collection.count())),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            res = self._collection.query(**kwargs)
        except Exception as e:
            logger.warning(f"Chroma query failed: {e}")
            return []

        results: list[tuple[ChunkRecord, float]] = []
        if not res or not res["ids"] or not res["ids"][0]:
            return []

        for cid, doc, meta, dist in zip(
            res["ids"][0],
            res["documents"][0],
            res["metadatas"][0],
            res["distances"][0],
            strict=False,
        ):
            # Convert cosine distance to similarity score in [0.0, 1.0]
            # dist is typically between 0 (identical) and 2 (opposite)
            sim_score = max(0.0, min(1.0, 1.0 - (float(dist) / 2.0)))
            chunk = ChunkRecord(
                chunk_id=cid,
                doc_id=meta.get("doc_id", ""),
                source=meta.get("source", ""),
                title=meta.get("title", ""),
                insurer=meta.get("insurer") or None,
                doc_type=meta.get("doc_type", "policy"),
                page=meta.get("page") or None,
                section=meta.get("section", ""),
                chunk_index=meta.get("chunk_index", 0),
                scope=meta.get("scope", "curated"),
                user_id=meta.get("user_id") or None,
                content=doc,
                content_sha256=meta.get("content_sha256", ""),
            )
            results.append((chunk, sim_score))

        return results

    def get_all_chunks(self) -> list[ChunkRecord]:
        """Retrieve all indexed chunks from collection (for BM25 indexing)."""
        count = self._collection.count()
        if count == 0:
            return []

        # Retrieve in batches or single get
        res = self._collection.get(include=["documents", "metadatas"])
        chunks: list[ChunkRecord] = []
        if not res or not res["ids"]:
            return []

        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"], strict=False):
            chunks.append(
                ChunkRecord(
                    chunk_id=cid,
                    doc_id=meta.get("doc_id", ""),
                    source=meta.get("source", ""),
                    title=meta.get("title", ""),
                    insurer=meta.get("insurer") or None,
                    doc_type=meta.get("doc_type", "policy"),
                    page=meta.get("page") or None,
                    section=meta.get("section", ""),
                    chunk_index=meta.get("chunk_index", 0),
                    scope=meta.get("scope", "curated"),
                    user_id=meta.get("user_id") or None,
                    content=doc,
                    content_sha256=meta.get("content_sha256", ""),
                )
            )
        return chunks

    def get_stats(self) -> dict[str, Any]:
        """Return statistics on indexed chunks."""
        total = self._collection.count()
        return {
            "total_chunks": total,
            "collection": self.collection_name,
            "persist_path": self.persist_path,
        }


_chroma_store: ChromaStore | None = None


def get_chroma_store(
    persist_path: str | None = None,
    collection_name: str | None = None,
) -> ChromaStore:
    global _chroma_store
    target_path = persist_path or settings.CHROMA_PATH
    target_coll = collection_name or settings.CHROMA_COLLECTION
    if (
        _chroma_store is None
        or _chroma_store.persist_path != target_path
        or _chroma_store.collection_name != target_coll
    ):
        _chroma_store = ChromaStore(persist_path=target_path, collection_name=target_coll)
    return _chroma_store


def reset_chroma_store() -> None:
    global _chroma_store
    _chroma_store = None
