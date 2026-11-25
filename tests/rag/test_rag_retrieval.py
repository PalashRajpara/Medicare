"""Tests for HybridRetriever combining dense vector search and sparse BM25 with RRF."""

from medicare.rag.bm25 import BM25Index
from medicare.rag.models import ChunkRecord
from medicare.rag.retriever import HybridRetriever, _jaccard_similarity
from medicare.rag.store import ChromaStore


def test_jaccard_similarity_calculation():
    """Verify token-level Jaccard similarity helper for near-duplicate deduplication."""
    s1 = "Waiting period for joint replacement is two years"
    s2 = "Waiting period for joint replacement is 24 months"
    s3 = "Completely different text about emergency ambulance services"

    sim_high = _jaccard_similarity(s1, s2)
    sim_low = _jaccard_similarity(s1, s3)

    assert sim_high > 0.4
    assert sim_low == 0.0


def test_hybrid_retrieval_rrf_scoring(tmp_path):
    """Verify dense and BM25 results merge using Reciprocal Rank Fusion."""
    chroma_dir = str(tmp_path / "chroma_rrf")
    store = ChromaStore(persist_path=chroma_dir, collection_name="test_rrf")
    bm25 = BM25Index()

    chunks = [
        ChunkRecord(
            chunk_id="c1",
            doc_id="d1",
            source="Policy1.md",
            title="Policy 1",
            content="Initial waiting period is 30 days for all illnesses except accidents.",
            content_sha256="sha1",
            scope="curated",
            insurer="star health",
        ),
        ChunkRecord(
            chunk_id="c2",
            doc_id="d2",
            source="Policy2.md",
            title="Policy 2",
            content="Pre-existing disease coverage begins after 36 months of continuous coverage.",
            content_sha256="sha2",
            scope="curated",
            insurer="hdfc ergo",
        ),
    ]

    store.upsert_chunks(chunks)
    bm25.build(chunks)

    retriever = HybridRetriever(chroma_store=store, bm25_index=bm25)

    hits = retriever.search(query="waiting period for pre-existing disease", top_k=2)

    assert len(hits) > 0
    assert hits[0].score > 0.0
    assert hits[0].chunk.chunk_id in ("c1", "c2")
