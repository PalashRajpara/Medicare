"""Embedding backends for multi-format RAG retrieval."""

import hashlib
import logging
import math
import re
from typing import Protocol

from medicare.config import settings

logger = logging.getLogger(__name__)


class EmbeddingBackend(Protocol):
    """Protocol for document and query embedding generators."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbeddingBackend:
    """Deterministic hash-based embedding backend for tests, offline CI, and fallback."""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def _hash_vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return vec

        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h // self.dim) % 2 == 0 else -1.0
            vec[idx] += sign

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._hash_vector(text)


class ChromaDefaultEmbeddingBackend:
    """ChromaDB default MiniLM ONNX embedding function with automatic graceful fallback."""

    def __init__(self) -> None:
        self._fn = None
        self._fallback = HashEmbeddingBackend()
        self._initialized = False

    def _get_fn(self):
        if not self._initialized:
            self._initialized = True
            try:
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

                self._fn = DefaultEmbeddingFunction()
            except Exception as e:
                logger.warning(
                    f"Chroma default embedding function could not be initialized: {e}. Falling back to HashEmbeddingBackend."
                )
                self._fn = None
        return self._fn

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        fn = self._get_fn()
        if fn is not None:
            try:
                return fn(texts)
            except Exception as e:
                logger.warning(f"Error computing Chroma embeddings: {e}. Using fallback.")
        return self._fallback.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        fn = self._get_fn()
        if fn is not None:
            try:
                res = fn([text])
                return res[0]
            except Exception as e:
                logger.warning(f"Error computing Chroma query embedding: {e}. Using fallback.")
        return self._fallback.embed_query(text)


_embedding_backends: dict[str, EmbeddingBackend] = {}


def get_embedding_backend(name: str | None = None) -> EmbeddingBackend:
    """Factory retrieving or instantiating configured embedding backend."""
    backend_name = name or settings.EMBEDDING_BACKEND
    if backend_name not in _embedding_backends:
        if backend_name == "hash":
            _embedding_backends[backend_name] = HashEmbeddingBackend()
        else:
            _embedding_backends[backend_name] = ChromaDefaultEmbeddingBackend()
    return _embedding_backends[backend_name]
