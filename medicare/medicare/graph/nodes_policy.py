"""Nodes and execution handlers for the Corrective Agentic Policy RAG sub-graph."""

import logging
import re
from typing import Any, Literal, TypedDict

from langgraph.types import StreamWriter

from medicare.config import settings
from medicare.config_loader import get_intent_words, msg
from medicare.domain.protocols import ModelProviderProtocol
from medicare.medicare.graph.events import emit_status
from medicare.medicare.graph.state import Citation, SupervisorPlan
from medicare.medicare.prompts import (
    CHUNK_GRADER_PROMPT,
    call_json,
)
from medicare.rag.models import RetrievedChunk
from medicare.rag.retriever import HybridRetriever
from medicare.rag.safety import detect_injection

logger = logging.getLogger(__name__)


class PolicySubState(TypedDict, total=False):
    """Internal state for the corrective Policy RAG sub-graph."""

    question: str
    plan: SupervisorPlan
    user_id: str | None
    doc_scope: Literal["curated", "mine", "both"]
    search_query: str
    active_insurer: str | None
    insurer_fallback: bool
    retrieved_chunks: list[RetrievedChunk]
    relevant_chunks: list[RetrievedChunk]
    dropped_injections: int
    rewrites_used: int
    citations: list[Citation]
    no_evidence: bool
    index_empty: bool


async def plan_query_node(
    state: PolicySubState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Extract initial search query and insurer filter from plan."""
    emit_status(writer, "policy_agent", "running", "Planning policy search query...")
    plan = state.get("plan")
    question = state.get("question", "")

    search_query = plan.rewritten_question if plan and plan.rewritten_question else question
    active_insurer = plan.entities.get("insurer") if plan else None
    doc_scope = state.get("doc_scope") or (plan.doc_scope if plan else "both")

    return {
        "search_query": search_query,
        "active_insurer": active_insurer,
        "insurer_fallback": False,
        "rewrites_used": state.get("rewrites_used", 0),
        "doc_scope": doc_scope,
        "dropped_injections": 0,
        "citations": [],
        "no_evidence": False,
        "index_empty": False,
    }


async def retrieve_node(
    state: PolicySubState,
    retriever: HybridRetriever,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Execute hybrid search across dense Chroma embeddings and sparse BM25."""
    query = state.get("search_query", "")
    insurer = state.get("active_insurer")
    doc_scope = state.get("doc_scope", "both")
    user_id = state.get("user_id")

    emit_status(
        writer,
        "policy_agent",
        "running",
        f"Searching policy guidelines (query='{query[:40]}...')...",
    )

    chunks = retriever.search(
        query=query,
        insurer=insurer,
        doc_scope=doc_scope,
        user_id=user_id,
        top_k=settings.RAG_TOP_K,
    )

    index_empty = len(chunks) == 0 and retriever.chroma._collection.count() == 0
    return {
        "retrieved_chunks": chunks,
        "index_empty": index_empty,
    }


async def grade_chunks_node(
    state: PolicySubState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Filter retrieved chunks for indirect prompt injections and clinical relevance."""
    raw_chunks = state.get("retrieved_chunks", [])
    if not raw_chunks:
        return {"relevant_chunks": []}

    safe_chunks: list[RetrievedChunk] = []
    dropped_count = 0

    # 1. Safety check for prompt injection
    for rc in raw_chunks:
        is_inj, reason = detect_injection(rc.chunk.content)
        if is_inj:
            logger.warning(
                f"Dropping chunk {rc.chunk.chunk_id} due to indirect injection: {reason}"
            )
            dropped_count += 1
        else:
            safe_chunks.append(rc)

    # 2. Relevance grading
    relevant: list[RetrievedChunk] = []
    q_words = set(re.findall(r"\w+", state.get("question", "").lower()))

    for rc in safe_chunks:
        # In mock mode or offline testing: use lexical overlap / score floor
        if settings.USE_MOCK_MODELS or provider.__class__.__name__ == "MockModelEngine":
            c_words = set(re.findall(r"\w+", rc.chunk.content.lower()))
            overlap = len(q_words & c_words)
            if overlap >= 1 or rc.score >= 0.15:
                relevant.append(rc)
            continue

        # Live provider LLM relevance grading
        prompt = (
            f"{CHUNK_GRADER_PROMPT}\n\n"
            f"QUESTION: {state.get('question')}\n\n"
            f"CHUNK CONTENT: {rc.chunk.content}\n"
        )
        try:
            from pydantic import BaseModel

            class GradeResult(BaseModel):
                relevant: bool
                reason: str = ""

            grade_res = await call_json(GradeResult, prompt, provider, model=settings.GROQ_MODEL)
            if grade_res.relevant:
                relevant.append(rc)
        except Exception:
            # On parse failure, keep if score is strong
            if rc.score >= 0.2:
                relevant.append(rc)

    return {
        "relevant_chunks": relevant,
        "dropped_injections": state.get("dropped_injections", 0) + dropped_count,
    }


async def rewrite_query_node(
    state: PolicySubState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Broaden search query and optionally relax insurer filter on low retrieval."""
    rewrites_used = state.get("rewrites_used", 0) + 1
    emit_status(
        writer,
        "policy_agent",
        "retry",
        "Broadening policy search terms...",
        retry=rewrites_used,
        max_retries=settings.RAG_MAX_REWRITES,
    )

    active_insurer = state.get("active_insurer")
    insurer_fallback = state.get("insurer_fallback", False)

    # On first rewrite: drop insurer constraint if present
    if active_insurer and not insurer_fallback:
        return {
            "active_insurer": None,
            "insurer_fallback": True,
            "rewrites_used": rewrites_used,
        }

    # On subsequent rewrite: broaden query tokens
    curr_q = state.get("search_query", "")
    expansion = " ".join(get_intent_words().get("query_expansion_terms", []))
    broad_q = f"{curr_q} {expansion}".strip()

    return {
        "search_query": broad_q,
        "rewrites_used": rewrites_used,
        "active_insurer": None,
        "insurer_fallback": True,
    }


async def build_citations_node(
    state: PolicySubState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Convert verified relevant chunks into formal Citations with C1..Cn markers."""
    relevant = state.get("relevant_chunks", [])
    citations: list[Citation] = []

    for idx, rc in enumerate(relevant, start=1):
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

    emit_status(
        writer,
        "policy_agent",
        "done",
        msg("policy_retrieved_verified", count=len(citations)),
    )
    return {
        "citations": citations,
        "no_evidence": False,
    }


async def no_evidence_node(
    state: PolicySubState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Conclude retrieval when rewrites are exhausted without relevant evidence."""
    emit_status(
        writer,
        "policy_agent",
        "done",
        msg("fallback_no_policy_clauses"),
    )
    return {
        "citations": [],
        "no_evidence": True,
    }
