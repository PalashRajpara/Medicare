"""Document upload, status discovery, and deletion router with tenant isolation."""

import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel

from medicare.config import settings
from medicare.config_loader import msg
from medicare.rag.ingest import delete_document, ingest_path
from medicare.rag.manifest import get_manifest_repository
from medicare.rag.models import DocumentRecord
from medicare.security.auth import verify_bearer_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents & RAG"])


class DocumentUploadResponse(BaseModel):
    doc_id: str
    status: str
    message: str = "Document accepted for processing"


class DocumentDetailResponse(BaseModel):
    doc_id: str
    source: str
    filename: str = ""
    title: str
    scope: str
    user_id: str | None = None
    insurer: str | None = None
    doc_type: str
    pages: int
    chunks: int
    status: str
    error: str | None = None
    created_at: str


class CuratedDocumentSummary(BaseModel):
    doc_id: str
    source: str
    title: str
    insurer: str | None = None
    pages: int
    chunks: int


class DocumentListResponse(BaseModel):
    user_documents: list[DocumentDetailResponse]
    curated_documents: list[CuratedDocumentSummary]


def _sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename)
    name = name.lstrip(".")
    name = name.replace("/", "").replace("\\", "").replace("\x00", "")
    return name.strip() or "unnamed_document"


def _validate_magic_bytes(ext: str, header_bytes: bytes) -> None:
    if ext == ".pdf":
        if not header_bytes.startswith(b"%PDF"):
            raise HTTPException(
                status_code=400,
                detail=msg("magic_bytes_pdf_failed"),
            )
    elif ext == ".docx" and not header_bytes.startswith(b"PK\x03\x04"):
        raise HTTPException(
            status_code=400,
            detail=msg("magic_bytes_docx_failed"),
        )


def _get_resolved_user_id(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id: str | None = Query(None),
) -> str:
    return x_user_id or user_id or "default_user"


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=202,
    dependencies=[Depends(verify_bearer_auth)],
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    insurer: str | None = Form(None),
    doc_type: str = Form("policy"),
    user_id_form: str | None = Form(None, alias="user_id"),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id_query: str | None = Query(None, alias="user_id"),
) -> DocumentUploadResponse:
    """Upload a user document for structure-aware parsing and hybrid RAG indexing."""
    resolved_user = user_id_form or x_user_id or user_id_query or "default_user"
    clean_name = _sanitize_filename(file.filename or "uploaded_file")
    ext = os.path.splitext(clean_name)[1].lower()

    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension '{ext}'. Allowed: {settings.ALLOWED_UPLOAD_EXTENSIONS}",
        )

    # Check user quota
    manifest_repo = get_manifest_repository()
    existing_user_docs = manifest_repo.list_documents(user_id=resolved_user, scope="user")
    if len(existing_user_docs) >= settings.USER_DOCS_PER_USER_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"User document quota exceeded (maximum {settings.USER_DOCS_PER_USER_MAX} documents).",
        )

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    user_upload_dir = os.path.join(settings.UPLOAD_DIR, resolved_user, doc_id)
    os.makedirs(user_upload_dir, exist_ok=True)
    target_path = os.path.join(user_upload_dir, clean_name)

    # Stream file to disk while enforcing max bytes
    max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
    total_bytes = 0
    header_checked = False

    with open(target_path, "wb") as out_file:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            if not header_checked:
                _validate_magic_bytes(ext, chunk[:16])
                header_checked = True

            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                # Abort and remove partial file
                out_file.close()
                if os.path.exists(target_path):
                    os.remove(target_path)
                raise HTTPException(
                    status_code=400,
                    detail=f"{msg('file_size_exceeded')} ({settings.UPLOAD_MAX_MB} MB)",
                )
            out_file.write(chunk)

    # Initial manifest row
    created_at = datetime.now(UTC).isoformat()
    record = DocumentRecord(
        doc_id=doc_id,
        scope="user",
        user_id=resolved_user,
        path=target_path,
        source=clean_name,
        title=os.path.splitext(clean_name)[0].replace("_", " ").title(),
        insurer=insurer,
        doc_type=doc_type,
        sha256="",
        pages=1,
        chunks=0,
        status="processing",
        created_at=created_at,
    )
    manifest_repo.upsert_document(record)

    # Ingest in background task
    def _run_bg_ingest():
        try:
            ingest_path(
                path=target_path,
                scope="user",
                user_id=resolved_user,
                insurer=insurer,
                doc_type=doc_type,
                custom_doc_id=doc_id,
                custom_source=clean_name,
            )
        except Exception as e:
            logger.error(f"Background ingest failed for doc_id {doc_id}: {e}")

    background_tasks.add_task(_run_bg_ingest)

    return DocumentUploadResponse(
        doc_id=doc_id,
        status="processing",
        message=msg("doc_uploaded_success"),
    )


@router.get(
    "/{doc_id}",
    response_model=DocumentDetailResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def get_document_status(
    doc_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id: str | None = Query(None),
) -> DocumentDetailResponse:
    """Retrieve indexing status and page/chunk details for a specific document."""
    resolved_user = x_user_id or user_id or "default_user"
    manifest_repo = get_manifest_repository()
    doc = manifest_repo.get_document(doc_id)

    # Never return 403 to avoid leaking document existence
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.scope == "user" and doc.user_id != resolved_user:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentDetailResponse(
        doc_id=doc.doc_id,
        source=doc.source,
        filename=doc.source,
        title=doc.title,
        scope=doc.scope,
        user_id=doc.user_id,
        insurer=doc.insurer,
        doc_type=doc.doc_type,
        pages=doc.pages,
        chunks=doc.chunks,
        status=doc.status,
        error=doc.error,
        created_at=doc.created_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def list_documents(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id: str | None = Query(None),
) -> DocumentListResponse:
    """List authenticated user's documents plus summary of curated public documents."""
    resolved_user = x_user_id or user_id or "default_user"
    manifest_repo = get_manifest_repository()

    user_docs = manifest_repo.list_documents(user_id=resolved_user, scope="user")
    curated_docs = manifest_repo.list_documents(scope="curated")

    user_details = [
        DocumentDetailResponse(
            doc_id=d.doc_id,
            source=d.source,
            filename=d.source,
            title=d.title,
            scope=d.scope,
            user_id=d.user_id,
            insurer=d.insurer,
            doc_type=d.doc_type,
            pages=d.pages,
            chunks=d.chunks,
            status=d.status,
            error=d.error,
            created_at=d.created_at,
        )
        for d in user_docs
    ]

    curated_summaries = [
        CuratedDocumentSummary(
            doc_id=d.doc_id,
            source=d.source,
            title=d.title,
            insurer=d.insurer,
            pages=d.pages,
            chunks=d.chunks,
        )
        for d in curated_docs
    ]

    return DocumentListResponse(
        user_documents=user_details,
        curated_documents=curated_summaries,
    )


@router.delete(
    "/{doc_id}",
    dependencies=[Depends(verify_bearer_auth)],
)
async def delete_user_document(
    doc_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id: str | None = Query(None),
) -> dict[str, str]:
    """Delete a user-owned document and its associated vectors and chunks."""
    resolved_user = x_user_id or user_id or "default_user"
    manifest_repo = get_manifest_repository()
    doc = manifest_repo.get_document(doc_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.scope == "curated":
        raise HTTPException(status_code=400, detail=msg("curated_cannot_delete"))
    if doc.user_id != resolved_user:
        raise HTTPException(status_code=404, detail="Document not found")

    success = delete_document(doc_id, user_id=resolved_user)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or delete failed")

    return {"status": "deleted", "doc_id": doc_id}
