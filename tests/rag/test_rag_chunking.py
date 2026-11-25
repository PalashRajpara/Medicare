"""Tests for structure-aware document chunking."""

from medicare.rag.chunking import chunk_document
from medicare.rag.models import DocumentRecord, PageText


def test_chunk_document_deterministic_ids_and_boundaries():
    """Verify chunking produces deterministic SHA-256 chunk IDs within size bounds."""
    doc = DocumentRecord(
        doc_id="doc_test_123",
        user_id="u_alpha",
        scope="curated",
        filename="policy.md",
        file_extension="md",
        content_sha256="abc123sha",
        title="Sample Policy",
        doc_type="policy",
        insurer="Star Health",
    )

    pages = [
        PageText(
            page=1,
            text="General guidelines on hospital admission. All patients must submit pre-auth documents 48 hours prior.",
            heading_path=["Admission Guidelines"],
        ),
        PageText(
            page=2,
            text="Waiting period rules. Initial waiting period is 30 days. Pre-existing disease waiting period is 36 months.",
            heading_path=["Waiting Periods"],
        ),
    ]

    chunks = chunk_document(doc, pages, target_chunk_size=400, overlap=50)

    assert len(chunks) >= 2
    for c in chunks:
        assert c.chunk_id.startswith(f"{doc.doc_id}-")
        assert len(c.content_sha256) == 64
        assert c.doc_id == doc.doc_id
        assert c.insurer == "star health"

    # Verify determinism: re-chunking same doc yields exact same IDs
    chunks2 = chunk_document(doc, pages, target_chunk_size=400, overlap=50)
    assert [c.chunk_id for c in chunks] == [c.chunk_id for c in chunks2]


def test_chunking_preserves_page_numbers_without_cross_page_splitting():
    """Verify chunks do not cross physical page boundaries."""
    doc = DocumentRecord(
        doc_id="doc_pages_456",
        user_id="u_beta",
        scope="user",
        filename="record.pdf",
        file_extension="pdf",
        content_sha256="xyz789sha",
        title="Patient Record",
        doc_type="bill",
    )

    pages = [
        PageText(page=1, text="Page one summary data.", heading_path=["P1"]),
        PageText(page=2, text="Page two itemized billing details.", heading_path=["P2"]),
    ]

    chunks = chunk_document(doc, pages, target_chunk_size=500, overlap=50)

    p1_chunks = [c for c in chunks if c.page == 1]
    p2_chunks = [c for c in chunks if c.page == 2]

    assert len(p1_chunks) >= 1
    assert len(p2_chunks) >= 1
    assert all("Page two" not in c.content for c in p1_chunks)
    assert all("Page one" not in c.content for c in p2_chunks)
