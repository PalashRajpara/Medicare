"""Tests for PolicySearchTool and PolicyRAGAgent."""

import pytest

from medicare.medicare.dataset.policy_indexer import index_markdown_policies
from medicare.tools.policy_search import PolicySearchTool


@pytest.fixture
def indexed_policy_store(tmp_path, monkeypatch):
    chroma_dir = str(tmp_path / "chroma_test")
    policies_dir = "tests/fixtures/medicare/policies"
    coll_name = "test_policies"
    manifest_db = str(tmp_path / "manifest.db")

    from medicare.config import settings
    from medicare.rag.store import reset_chroma_store

    monkeypatch.setattr(settings, "CHROMA_PATH", chroma_dir)
    monkeypatch.setattr(settings, "CHROMA_COLLECTION", coll_name)
    monkeypatch.setattr(settings, "MANIFEST_DB_PATH", manifest_db)
    reset_chroma_store()

    index_markdown_policies(
        policy_dir=policies_dir, chroma_path=chroma_dir, collection_name=coll_name
    )
    return chroma_dir, coll_name


def test_policy_retrieval_with_citations(indexed_policy_store):
    chroma_dir, coll_name = indexed_policy_store
    tool = PolicySearchTool(chroma_path=chroma_dir, collection_name=coll_name)

    citations = tool.search("What is the waiting period for joint replacement?", top_k=3)
    assert len(citations) > 0
    c = citations[0]
    assert c.source != ""
    assert c.section != ""
    assert "waiting period" in c.text.lower() or "joint" in c.text.lower()
    assert 0.0 <= c.score <= 1.0


def test_policy_retrieval_insurer_filter(indexed_policy_store):
    chroma_dir, coll_name = indexed_policy_store
    tool = PolicySearchTool(chroma_path=chroma_dir, collection_name=coll_name)

    citations = tool.search("pre-existing disease waiting period", insurer="hdfc ergo", top_k=3)
    assert len(citations) > 0
    for c in citations:
        assert "hdfc" in c.source.lower()


def test_empty_policy_index_handled_gracefully(tmp_path):
    empty_chroma = str(tmp_path / "empty_chroma")
    tool = PolicySearchTool(chroma_path=empty_chroma, collection_name="empty_coll")

    citations = tool.search("room rent capping", top_k=5)
    assert citations == []


def test_chroma_unavailable_fallback(monkeypatch):
    """Simulate ChromaDB import/init failure and ensure fallback activates without crashing."""
    import sys

    # Monkeypatch chromadb to fail
    monkeypatch.setitem(sys.modules, "chromadb", None)

    tool = PolicySearchTool(chroma_path="/invalid/path", collection_name="test")
    assert tool.is_fallback is True
    # Should not raise exception
    res = tool.search("emergency hospitalization")
    assert isinstance(res, list)
