"""In-memory BM25 sparse search index for hybrid retrieval."""

import re
import threading
from collections.abc import Callable

from rank_bm25 import BM25Okapi

from medicare.rag.models import ChunkRecord


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    return re.findall(r"\w+", text.lower())


class BM25Index:
    """Thread-safe BM25Okapi sparse retrieval index over ChunkRecord items."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: list[ChunkRecord] = []
        self._corpus_tokens: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    def refresh(self, chunks: list[ChunkRecord]) -> None:
        """Rebuild the BM25 index from a collection of ChunkRecords."""
        with self._lock:
            self._chunks = list(chunks)
            if not self._chunks:
                self._corpus_tokens = []
                self._bm25 = None
                return

            self._corpus_tokens = [_tokenize(c.content) for c in self._chunks]
            # Ensure at least some tokens exist
            if any(self._corpus_tokens):
                self._bm25 = BM25Okapi(self._corpus_tokens)
            else:
                self._bm25 = None

    def build(self, chunks: list[ChunkRecord]) -> None:
        """Build or rebuild the BM25 index from a list of ChunkRecords."""
        self.refresh(chunks)

    def search(
        self,
        query: str,
        top_k: int = 20,
        filter_fn: Callable[[ChunkRecord], bool] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        """Search BM25 index returning ranked (ChunkRecord, normalized_score) tuples."""
        with self._lock:
            if self._bm25 is None or not self._chunks:
                return []

            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            scores = self._bm25.get_scores(query_tokens)
            max_score = max(scores) if len(scores) > 0 and max(scores) > 0 else 1.0

            scored_chunks: list[tuple[ChunkRecord, float]] = []
            for chunk, raw_score in zip(self._chunks, scores, strict=False):
                if raw_score <= 0.0:
                    continue
                if filter_fn is not None and not filter_fn(chunk):
                    continue
                normalized_score = min(1.0, float(raw_score) / max_score)
                scored_chunks.append((chunk, normalized_score))

            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            return scored_chunks[:top_k]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._chunks)


_bm25_index = BM25Index()


def get_bm25_index() -> BM25Index:
    return _bm25_index
