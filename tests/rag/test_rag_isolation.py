"""Tests for multi-tenant document isolation in hybrid RAG retriever."""

from medicare.rag.bm25 import BM25Index
from medicare.rag.models import ChunkRecord
from medicare.rag.retriever import HybridRetriever
from medicare.rag.store import ChromaStore


def test_tenant_isolation_user_a_cannot_see_user_b_chunks(tmp_path):
    """Verify strict tenant isolation: User A never retrieves User B's documents."""
    chroma_dir = str(tmp_path / "chroma_iso")
    store = ChromaStore(persist_path=chroma_dir, collection_name="test_iso")
    bm25 = BM25Index()

    chunks = [
        ChunkRecord(
            chunk_id="chunk_curated",
            doc_id="d_curated",
            source="Public_Policy.md",
            title="Public Policy",
            content="Curated insurance clause on cataract surgery waiting period.",
            content_sha256="sha_curated",
            scope="curated",
            user_id=None,
        ),
        ChunkRecord(
            chunk_id="chunk_alice",
            doc_id="d_alice",
            source="Alice_Discharge.pdf",
            title="Alice Discharge Summary",
            content="Patient Alice private medical bill total ₹75,000 paid by insurance.",
            content_sha256="sha_alice",
            scope="user",
            user_id="user_alice",
        ),
        ChunkRecord(
            chunk_id="chunk_bob",
            doc_id="d_bob",
            source="Bob_Prescription.pdf",
            title="Bob Prescription",
            content="Patient Bob private confidential medical diagnosis report.",
            content_sha256="sha_bob",
            scope="user",
            user_id="user_bob",
        ),
    ]

    store.upsert_chunks(chunks)
    bm25.build(chunks)

    retriever = HybridRetriever(chroma_store=store, bm25_index=bm25)

    # 1. User Alice searching with scope="both": sees curated + alice, NEVER bob
    alice_hits = retriever.search(
        query="medical bill patient", user_id="user_alice", doc_scope="both"
    )
    hit_ids = [h.chunk.chunk_id for h in alice_hits]
    assert "chunk_alice" in hit_ids
    assert "chunk_bob" not in hit_ids, (
        "CRITICAL: Tenant leakage detected! User Alice saw Bob's chunk"
    )

    # 2. User Bob searching with scope="mine": sees ONLY bob, NOT alice, NOT curated
    bob_hits = retriever.search(
        query="medical diagnosis report", user_id="user_bob", doc_scope="mine"
    )
    bob_ids = [h.chunk.chunk_id for h in bob_hits]
    assert "chunk_bob" in bob_ids
    assert "chunk_alice" not in bob_ids
    assert "chunk_curated" not in bob_ids

    # 3. Anonymous/Unauthenticated searching curated only: sees curated, NEVER user documents
    anon_hits = retriever.search(query="cataract surgery", doc_scope="curated")
    anon_ids = [h.chunk.chunk_id for h in anon_hits]
    assert "chunk_alice" not in anon_ids
    assert "chunk_bob" not in anon_ids
