"""Heading-aware Markdown policy chunker and multi-format vector indexer."""

import logging
import re
from pathlib import Path
from typing import Any

from medicare.rag.ingest import ingest_directory

logger = logging.getLogger(__name__)


def chunk_markdown_document(
    text: str, source_name: str, target_chunk_size: int = 750, overlap: int = 100
) -> list[dict[str, Any]]:
    """Chunk Markdown document preserving nearest heading as section metadata."""
    lines = text.split("\n")
    current_heading = "General Policy Guidelines"
    chunks: list[dict[str, Any]] = []

    current_buffer: list[str] = []
    current_length = 0

    for line in lines:
        heading_match = re.match(r"^(#{1,3})\s+(.*)$", line.strip())
        if heading_match:
            # New section encountered
            if current_buffer:
                chunk_text = "\n".join(current_buffer).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "source": source_name,
                            "section": current_heading,
                        }
                    )
                current_buffer = []
                current_length = 0
            current_heading = heading_match.group(2).strip()
            continue

        if line.strip():
            current_buffer.append(line)
            current_length += len(line) + 1

            if current_length >= target_chunk_size:
                chunk_text = "\n".join(current_buffer).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "source": source_name,
                            "section": current_heading,
                        }
                    )
                if len(current_buffer) > 1:
                    current_buffer = [current_buffer[-1]]
                    current_length = len(current_buffer[-1])
                else:
                    current_buffer = []
                    current_length = 0

    if current_buffer:
        chunk_text = "\n".join(current_buffer).strip()
        if chunk_text:
            chunks.append(
                {
                    "text": chunk_text,
                    "source": source_name,
                    "section": current_heading,
                }
            )

    return chunks


def index_policy_documents(
    policies_dir: str,
    chroma_path: str,
    collection_name: str,
    sync: bool = False,
    reindex_all: bool = False,
) -> dict[str, Any]:
    """Index all supported policy documents using the multi-format RAG ingestion pipeline."""
    dir_path = Path(policies_dir)
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        return {"indexed_files": 0, "total_chunks": 0}

    # Also support old Chroma direct indexing for backward-compat test fixtures if needed
    try:
        import chromadb

        client = chromadb.PersistentClient(path=chroma_path)
        coll = client.get_or_create_collection(name=collection_name)

        md_files = sorted(list(dir_path.glob("*.md")))
        all_chunks: list[dict[str, Any]] = []
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                doc_chunks = chunk_markdown_document(content, md_file.name)
                all_chunks.extend(doc_chunks)
            except Exception as e:
                logger.error(f"Error reading policy file {md_file}: {e}")

        if all_chunks:
            ids = [f"{c['source']}-{idx}" for idx, c in enumerate(all_chunks)]
            documents = [c["text"] for c in all_chunks]
            metadatas = []
            from medicare.rag.ingest import _infer_insurer_from_path

            for c in all_chunks:
                ins = _infer_insurer_from_path(c["source"]) or "general"
                metadatas.append(
                    {"source": c["source"], "section": c["section"], "insurer": ins.lower()}
                )

            for i in range(0, len(ids), 100):
                coll.upsert(
                    ids=ids[i : i + 100],
                    documents=documents[i : i + 100],
                    metadatas=metadatas[i : i + 100],
                )
    except Exception as e:
        logger.warning(f"Direct chroma index note: {e}")

    # Run full multi-format RAG ingestion pipeline
    res = ingest_directory(
        policies_dir,
        sync=sync,
        reindex_all=reindex_all,
        chroma_path=chroma_path,
        collection_name=collection_name,
    )
    return {
        "indexed_files": res["total_found"],
        "total_chunks": res["ingested"],
        "failed": res["failed"],
        "deleted": res["deleted"],
    }


def index_markdown_policies(
    policy_dir: str, chroma_path: str, collection_name: str
) -> dict[str, Any]:
    """Convenience alias for index_policy_documents."""
    return index_policy_documents(
        policies_dir=policy_dir, chroma_path=chroma_path, collection_name=collection_name
    )


def chunk_markdown_file(file_path: str) -> list[Any]:
    """Convenience chunker for a single file returning Citation items."""
    from medicare.domain.models import Citation

    p = Path(file_path)
    content = p.read_text(encoding="utf-8")
    raw_chunks = chunk_markdown_document(content, p.name)
    return [
        Citation(
            source=c["source"],
            section=c["section"],
            text=c["text"],
            score=1.0,
        )
        for c in raw_chunks
    ]
