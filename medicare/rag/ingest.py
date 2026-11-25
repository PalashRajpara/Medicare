"""Ingestion service for multi-format documents into Chroma and BM25."""

import hashlib
import logging
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from medicare.config import settings
from medicare.rag.bm25 import get_bm25_index
from medicare.rag.chunking import chunk_document
from medicare.rag.loaders import loader_registry
from medicare.rag.manifest import get_manifest_repository
from medicare.rag.models import DocumentRecord
from medicare.rag.store import get_chroma_store

logger = logging.getLogger(__name__)


def _compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _infer_insurer_from_path(path: str) -> str | None:
    """Infer insurance provider name dynamically from folder hierarchy, database, seed CSVs, or filename."""
    norm = os.path.normpath(path).replace("\\", "/")
    parts = norm.split("/")
    # Check if inside a subfolder under policies (e.g. data/policies/<Insurer>/policy.pdf)
    if "policies" in parts:
        idx = parts.index("policies")
        if idx + 1 < len(parts) - 1:
            raw_folder = parts[idx + 1].replace("_", " ").title()
            return raw_folder

    fname = os.path.splitext(os.path.basename(path))[0]
    fname_clean = fname.lower().replace("_", "").replace("-", "")

    # Match against known insurers dynamically discovered by DB tools
    try:
        from medicare.tools.db_tools import get_known_catalog

        _, _, insurers_map = get_known_catalog()
        for ins_key, ins_val in sorted(insurers_map.items(), key=lambda x: len(x[0]), reverse=True):
            if ins_key.replace(" ", "") in fname_clean:
                return ins_val.title()
    except Exception:
        pass

    # Fallback to deriving from filename before 'policy' / 'guidelines'
    clean_name = re.sub(r"(?i)[-_]?(policy|guideline|terms|rules).*", "", fname)
    clean_name = clean_name.replace("_", " ").replace("-", " ").strip()
    return clean_name.title() if clean_name else None


def ingest_path(
    path: str,
    scope: Literal["curated", "user"] = "curated",
    user_id: str | None = None,
    insurer: str | None = None,
    doc_type: str = "policy",
    force_reindex: bool = False,
    custom_doc_id: str | None = None,
    custom_source: str | None = None,
    chroma_path: str | None = None,
    collection_name: str | None = None,
    manifest_db: str | None = None,
) -> DocumentRecord:
    """Ingest a single document file into manifest, Chroma vector store, and BM25."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    loader_fn = loader_registry.get_loader(ext)
    file_sha = _compute_sha256(path)
    source_name = custom_source or os.path.basename(path)
    title = os.path.splitext(source_name)[0].replace("_", " ").title()
    inferred_insurer = insurer or _infer_insurer_from_path(path)

    doc_id = custom_doc_id or (
        hashlib.sha256(f"{scope}_{path}".encode()).hexdigest()[:16]
        if scope == "curated"
        else f"doc_{uuid.uuid4().hex[:12]}"
    )

    manifest_repo = get_manifest_repository(manifest_db)
    existing_record = manifest_repo.get_document(doc_id)
    if existing_record and existing_record.sha256 == file_sha and not force_reindex:
        return existing_record

    created_at = datetime.now(UTC).isoformat()
    doc_record = DocumentRecord(
        doc_id=doc_id,
        scope=scope,
        user_id=user_id,
        path=path,
        source=source_name,
        title=title,
        insurer=inferred_insurer,
        doc_type=doc_type,
        sha256=file_sha,
        pages=1,
        chunks=0,
        status="processing",
        created_at=created_at,
    )

    try:
        pages = loader_fn(path)
        doc_record.pages = len(pages)

        # Chunk document
        chunks = chunk_document(doc_record, pages)
        doc_record.chunks = len(chunks)

        # Upsert into Chroma
        chroma = get_chroma_store(persist_path=chroma_path, collection_name=collection_name)
        # Delete old chunks for this doc_id if reindexing
        chroma.delete_by_doc_id(doc_id)
        chroma.upsert_chunks(chunks)

        # Update status
        doc_record.status = "ready"
        manifest_repo.upsert_document(doc_record)

        # Refresh BM25
        bm25 = get_bm25_index()
        all_chunks = chroma.get_all_chunks()
        bm25.refresh(all_chunks)

        return doc_record
    except Exception as e:
        logger.error(f"Failed to ingest document {path}: {e}")
        doc_record.status = "failed"
        doc_record.error = str(e)
        manifest_repo.upsert_document(doc_record)
        return doc_record


def ingest_directory(
    dir_path: str,
    sync: bool = False,
    reindex_all: bool = False,
    chroma_path: str | None = None,
    collection_name: str | None = None,
    manifest_db: str | None = None,
) -> dict[str, Any]:
    """Ingest all supported documents within a directory recursively."""
    if not os.path.exists(dir_path):
        logger.warning(f"Directory {dir_path} does not exist; skipping ingestion.")
        return {"total_found": 0, "ingested": 0, "failed": 0, "deleted": 0}

    manifest_repo = get_manifest_repository(manifest_db)
    chroma = get_chroma_store(persist_path=chroma_path, collection_name=collection_name)

    found_files: list[str] = []
    for root, _, files in os.walk(dir_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in settings.ALLOWED_UPLOAD_EXTENSIONS:
                found_files.append(os.path.join(root, f))

    ingested_count = 0
    failed_count = 0
    synced_doc_ids: set[str] = set()

    for file_path in found_files:
        doc = ingest_path(
            file_path,
            scope="curated",
            force_reindex=reindex_all,
            chroma_path=chroma_path,
            collection_name=collection_name,
            manifest_db=manifest_db,
        )
        synced_doc_ids.add(doc.doc_id)
        if doc.status == "ready":
            ingested_count += 1
        else:
            failed_count += 1

    deleted_count = 0
    if sync:
        existing_docs = manifest_repo.list_documents(scope="curated")
        for ed in existing_docs:
            if ed.doc_id not in synced_doc_ids and not os.path.exists(ed.path):
                delete_document(ed.doc_id)
                deleted_count += 1

    # Final BM25 refresh
    all_chunks = chroma.get_all_chunks()
    get_bm25_index().refresh(all_chunks)

    return {
        "total_found": len(found_files),
        "ingested": ingested_count,
        "failed": failed_count,
        "deleted": deleted_count,
    }


def delete_document(doc_id: str, user_id: str | None = None) -> bool:
    """Delete a document, its disk file (for user docs), and all indexed chunks."""
    manifest_repo = get_manifest_repository()
    doc = manifest_repo.get_document(doc_id)
    if not doc:
        return False

    # Enforce tenant ownership for user documents
    if user_id and doc.user_id != user_id:
        return False

    # Prevent API deletion of curated system documents
    if doc.scope == "curated" and user_id is not None:
        return False

    chroma = get_chroma_store()
    chroma.delete_by_doc_id(doc_id)
    manifest_repo.delete_document(doc_id, user_id=user_id)

    # Delete original disk file if it was a user upload
    if doc.scope == "user" and os.path.exists(doc.path):
        try:
            os.remove(doc.path)
            parent_dir = os.path.dirname(doc.path)
            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
        except Exception as e:
            logger.warning(f"Could not remove disk file {doc.path}: {e}")

    # Refresh BM25
    get_bm25_index().refresh(chroma.get_all_chunks())
    return True
