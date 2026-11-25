"""Semantic vector store tool for enterprise knowledge base question answering."""

import hashlib
import math
from typing import Any

from medicare.tools.base import BaseTool


def _simple_embedding(text: str, dim: int = 64) -> list[float]:
    """Deterministic term-frequency hash embedding for standalone execution."""
    vec = [0.0] * dim
    words = text.lower().split()
    for w in words:
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16) % dim
        vec[h] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    return sum(a * b for a, b in zip(v1, v2))


DEFAULT_DOCUMENTS = [
    {
        "id": "doc-01",
        "title": "Employee Handbook - Remote Work Policy",
        "source": "https://intranet.company.internal/policies/remote-work.pdf",
        "content": "All employees are eligible for hybrid remote work up to 3 days per week with manager approval. Working from abroad requires 30 days prior notice to People Ops.",
    },
    {
        "id": "doc-02",
        "title": "Expense Guidelines 2026",
        "source": "https://intranet.company.internal/finance/expenses.pdf",
        "content": "Daily meal allowance on domestic business travel is capped at $75 per day. Itemized receipts are mandatory for any expense exceeding $25.",
    },
    {
        "id": "doc-03",
        "title": "Security & Laptop Encryption",
        "source": "https://intranet.company.internal/security/laptop-policy.pdf",
        "content": "Full disk encryption (FileVault / BitLocker) must remain enabled at all times. Company laptops must not be connected to untrusted public Wi-Fi without VPN.",
    },
]


class VectorStoreRAGTool(BaseTool):
    """Tool for querying corporate policy vector database."""

    name = "vector_rag"
    description = "Search enterprise document repository for corporate policies and handbooks."

    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self.documents = documents or DEFAULT_DOCUMENTS

    async def execute(self, query: str = "", top_k: int = 2, **kwargs: Any) -> str:
        if not query:
            return "Error: Empty query for vector knowledge base."

        q_vec = _simple_embedding(query)
        scored = []
        for doc in self.documents:
            d_vec = _simple_embedding(doc["content"] + " " + doc["title"])
            score = _cosine_similarity(q_vec, d_vec)
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_docs = scored[:top_k]

        output = [f"Retrieved {len(top_docs)} Enterprise Documents:"]
        for score, doc in top_docs:
            output.append(
                f"- Document: [{doc['title']}]({doc['source']})\n"
                f"  Relevance Score: {score:.3f}\n"
                f"  Content: {doc['content']}"
            )

        return "\n\n".join(output)
