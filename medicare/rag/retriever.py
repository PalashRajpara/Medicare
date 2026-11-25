"""Hybrid retriever combining dense vector search and sparse BM25 with Reciprocal Rank Fusion."""

import logging
import re
from typing import Literal

from medicare.config import settings
from medicare.rag.bm25 import BM25Index, get_bm25_index
from medicare.rag.models import ChunkRecord, RetrievedChunk
from medicare.rag.store import ChromaStore, get_chroma_store

logger = logging.getLogger(__name__)


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute token-level Jaccard similarity between two texts."""
    tokens_a = set(re.findall(r"\w+", text_a.lower()))
    tokens_b = set(re.findall(r"\w+", text_b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


class HybridRetriever:
    """Orchestrates dense Chroma search and sparse BM25 with RRF and tenant isolation."""

    def __init__(
        self,
        chroma_store: ChromaStore | None = None,
        bm25_index: BM25Index | None = None,
    ) -> None:
        self.chroma = chroma_store or get_chroma_store()
        self.bm25 = bm25_index or get_bm25_index()

    def search(
        self,
        query: str,
        insurer: str | None = None,
        doc_scope: Literal["curated", "mine", "both"] = "both",
        user_id: str | None = None,
        doc_types: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Execute hybrid search with strict tenant isolation and reciprocal rank fusion.

        Tenant Isolation Guarantee:
            - curated scope: only curated documents
            - mine scope: only user documents matching user_id
            - both scope: curated documents + user documents matching user_id
            - Under NO circumstance are chunks with scope == "user" AND user_id != caller returned.
        """
        k = top_k or settings.RAG_TOP_K
        dense_k = settings.RAG_DENSE_K
        sparse_k = settings.RAG_SPARSE_K
        fetch_k = settings.RAG_FETCH_K
        rrf_k = settings.RAG_RRF_K

        def passes_scope_and_filters(chunk: ChunkRecord) -> bool:
            # 1. Tenant Scope Check
            if doc_scope == "curated":
                if chunk.scope != "curated":
                    return False
            elif doc_scope == "mine":
                if chunk.scope != "user" or not user_id or chunk.user_id != user_id:
                    return False
            else:  # "both"
                if chunk.scope == "user" and (not user_id or chunk.user_id != user_id):
                    return False

            # 2. Insurer Filter (if provided and chunk has insurer)
            if insurer and chunk.insurer and insurer.lower() not in chunk.insurer.lower():
                return False

            # 3. Document Types Filter
            return not (doc_types and chunk.doc_type not in doc_types)

        # Build Chroma WHERE clause
        chroma_where: dict | None = None
        if doc_scope == "curated":
            chroma_where = {"scope": "curated"}
        elif doc_scope == "mine" and user_id:
            chroma_where = {"$and": [{"scope": "user"}, {"user_id": user_id}]}

        # 1. Dense Search
        dense_results = self.chroma.search_dense(query, top_k=dense_k, where=chroma_where)

        # 2. Sparse BM25 Search
        sparse_results = self.bm25.search(query, top_k=sparse_k, filter_fn=passes_scope_and_filters)

        # 3. Reciprocal Rank Fusion
        # Mapping: chunk_id -> (ChunkRecord, rrf_score, dense_rank, sparse_rank)
        rrf_scores: dict[str, dict] = {}

        # Process dense ranks
        for rank, (chunk, _dense_sim) in enumerate(dense_results, start=1):
            if not passes_scope_and_filters(chunk):
                continue
            cid = chunk.chunk_id
            if cid not in rrf_scores:
                rrf_scores[cid] = {
                    "chunk": chunk,
                    "score": 0.0,
                    "dense_rank": rank,
                    "sparse_rank": None,
                }
            rrf_scores[cid]["score"] += 1.0 / (rrf_k + rank)

        # Process sparse ranks
        for rank, (chunk, _sparse_sim) in enumerate(sparse_results, start=1):
            if not passes_scope_and_filters(chunk):
                continue
            cid = chunk.chunk_id
            if cid not in rrf_scores:
                rrf_scores[cid] = {
                    "chunk": chunk,
                    "score": 0.0,
                    "dense_rank": None,
                    "sparse_rank": rank,
                }
            else:
                rrf_scores[cid]["sparse_rank"] = rank
            rrf_scores[cid]["score"] += 1.0 / (rrf_k + rank)

        if not rrf_scores:
            return []

        # Sort by fused RRF score descending
        fused_items = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
        top_candidates = fused_items[:fetch_k]

        # 4. Near-Duplicate Suppression (Jaccard > 0.9)
        deduped: list[dict] = []
        for cand in top_candidates:
            cand_text = cand["chunk"].content
            is_dup = False
            for kept in deduped:
                if _jaccard_similarity(cand_text, kept["chunk"].content) > 0.9:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(cand)
            if len(deduped) >= k:
                break

        # Normalize score into [0.0, 1.0]
        max_fused = max(item["score"] for item in deduped) if deduped else 1.0
        final_results: list[RetrievedChunk] = []
        for item in deduped:
            norm_score = min(1.0, float(item["score"]) / max_fused) if max_fused > 0 else 0.0
            final_results.append(
                RetrievedChunk(
                    chunk=item["chunk"],
                    score=norm_score,
                    dense_rank=item["dense_rank"],
                    sparse_rank=item["sparse_rank"],
                )
            )

        return final_results
