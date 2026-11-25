"""Structure-aware chunking for multi-format documents."""

import hashlib
import re
from typing import Any

from medicare.config import settings
from medicare.rag.models import ChunkRecord, DocumentRecord, PageText


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences while respecting common abbreviations."""
    # Split on period, question mark, or exclamation followed by whitespace
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_document(
    doc: DocumentRecord,
    pages: list[PageText],
    chunk_chars: int | None = None,
    overlap_chars: int | None = None,
    target_chunk_size: int | None = None,
    overlap: int | None = None,
    **kwargs: Any,
) -> list[ChunkRecord]:
    """Chunk document pages into structure-aware chunks.

    Respects headings, paragraphs, and sentence boundaries.
    Generates deterministic chunk IDs via SHA-256.
    """
    max_chars = target_chunk_size or chunk_chars or settings.RAG_CHUNK_CHARS
    overlap_sz = overlap if overlap is not None else (overlap_chars or settings.RAG_CHUNK_OVERLAP)

    chunks: list[ChunkRecord] = []
    chunk_index = 0
    insurer_clean = (doc.insurer or "").lower() or None

    for page in pages:
        section_title = " > ".join(page.heading_path) if page.heading_path else ""
        paragraphs = [p.strip() for p in page.text.split("\n\n") if p.strip()]

        current_text = ""
        for para in paragraphs:
            # Check if paragraph alone exceeds max_chars -> split by sentences
            if len(para) > max_chars:
                sentences = _split_into_sentences(para)
                for sentence in sentences:
                    if len(current_text) + len(sentence) + 1 <= max_chars:
                        current_text = (
                            f"{current_text} {sentence}".strip() if current_text else sentence
                        )
                    else:
                        if current_text:
                            content_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
                            chunk_id = f"{doc.doc_id}-{chunk_index}-{content_sha[:16]}"
                            chunks.append(
                                ChunkRecord(
                                    chunk_id=chunk_id,
                                    doc_id=doc.doc_id,
                                    source=doc.source,
                                    title=doc.title,
                                    insurer=insurer_clean,
                                    doc_type=doc.doc_type,
                                    page=page.page,
                                    section=section_title,
                                    chunk_index=chunk_index,
                                    scope=doc.scope,
                                    user_id=doc.user_id,
                                    content=current_text,
                                    content_sha256=content_sha,
                                )
                            )
                            chunk_index += 1
                            # Overlap from previous text
                            current_text = (
                                current_text[-overlap_sz:] + " " + sentence
                                if overlap_sz > 0
                                else sentence
                            ).strip()
                        else:
                            # Single sentence larger than max_chars
                            content_sha = hashlib.sha256(sentence.encode("utf-8")).hexdigest()
                            chunk_id = f"{doc.doc_id}-{chunk_index}-{content_sha[:16]}"
                            chunks.append(
                                ChunkRecord(
                                    chunk_id=chunk_id,
                                    doc_id=doc.doc_id,
                                    source=doc.source,
                                    title=doc.title,
                                    insurer=insurer_clean,
                                    doc_type=doc.doc_type,
                                    page=page.page,
                                    section=section_title,
                                    chunk_index=chunk_index,
                                    scope=doc.scope,
                                    user_id=doc.user_id,
                                    content=sentence,
                                    content_sha256=content_sha,
                                )
                            )
                            chunk_index += 1
                            current_text = ""
                continue

            # Standard paragraph accumulation
            if len(current_text) + len(para) + 2 <= max_chars:
                current_text = f"{current_text}\n\n{para}".strip() if current_text else para
            else:
                if current_text:
                    content_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
                    chunk_id = f"{doc.doc_id}-{chunk_index}-{content_sha[:16]}"
                    chunks.append(
                        ChunkRecord(
                            chunk_id=chunk_id,
                            doc_id=doc.doc_id,
                            source=doc.source,
                            title=doc.title,
                            insurer=insurer_clean,
                            doc_type=doc.doc_type,
                            page=page.page,
                            section=section_title,
                            chunk_index=chunk_index,
                            scope=doc.scope,
                            user_id=doc.user_id,
                            content=current_text,
                            content_sha256=content_sha,
                        )
                    )
                    chunk_index += 1
                    # Retain overlap from end of current_text
                    overlap_seed = current_text[-overlap_sz:] if overlap_sz > 0 else ""
                    current_text = f"{overlap_seed}\n\n{para}".strip() if overlap_seed else para
                else:
                    current_text = para

        if current_text:
            content_sha = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
            chunk_id = f"{doc.doc_id}-{chunk_index}-{content_sha[:16]}"
            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    source=doc.source,
                    title=doc.title,
                    insurer=insurer_clean,
                    doc_type=doc.doc_type,
                    page=page.page,
                    section=section_title,
                    chunk_index=chunk_index,
                    scope=doc.scope,
                    user_id=doc.user_id,
                    content=current_text,
                    content_sha256=content_sha,
                )
            )
            chunk_index += 1

    return chunks
