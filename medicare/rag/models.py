"""Data models for multi-format RAG ingestion, storage, and retrieval."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class PageText(BaseModel):
    """Raw text extracted from a specific page or section of a document."""

    page: int | None = None  # 1-based index where applicable
    text: str
    heading_path: list[str] = Field(default_factory=list)


class DocumentRecord(BaseModel):
    """Manifest record tracking an indexed document."""

    doc_id: str
    scope: Literal["curated", "user"] = "curated"
    user_id: str | None = None
    path: str = ""
    source: str = ""  # Display filename
    filename: str = ""
    file_extension: str = ""
    title: str = ""
    insurer: str | None = None
    doc_type: str = "policy"  # policy | brochure | claim_form | bill | other
    sha256: str = ""
    content_sha256: str = ""
    pages: int = 1
    chunks: int = 0
    status: Literal["processing", "ready", "failed"] = "ready"
    error: str | None = None
    created_at: str = ""

    def __init__(self, **data: Any) -> None:
        if "filename" in data and not data.get("source"):
            data["source"] = data["filename"]
        if "content_sha256" in data and not data.get("sha256"):
            data["sha256"] = data["content_sha256"]
        if "file_extension" in data and not data.get("path"):
            data["path"] = f"{data.get('doc_id', 'doc')}.{data['file_extension']}"
        super().__init__(**data)


class ChunkRecord(BaseModel):
    """Individual chunk indexed into vector store and BM25."""

    chunk_id: str
    doc_id: str
    source: str
    title: str
    insurer: str | None = None
    doc_type: str = "policy"
    page: int | None = None
    section: str = ""
    chunk_index: int = 0
    scope: Literal["curated", "user"] = "curated"
    user_id: str | None = None
    content: str
    content_sha256: str
    ingestion_version: int = 1


class RetrievedChunk(BaseModel):
    """A chunk retrieved from hybrid search with ranking metadata."""

    chunk: ChunkRecord
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
