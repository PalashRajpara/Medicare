"""MediCare status endpoint providing table row counts and policy chunk metrics."""

import os
import sqlite3
from importlib.metadata import version

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from medicare.config import settings
from medicare.medicare.dataset.schema import ALLOWED_TABLES
from medicare.rag.manifest import get_manifest_repository
from medicare.security.auth import verify_bearer_auth
from medicare.tools.policy_search import PolicySearchTool

try:
    _LANGGRAPH_VERSION = version("langgraph")
except Exception:
    _LANGGRAPH_VERSION = "unknown"

router = APIRouter(prefix="/medicare", tags=["MediCare Navigator"])


class MedicareStatusResponse(BaseModel):
    """Status payload for hospital database and policy vector storage."""

    db_exists: bool
    tables: dict[str, int]
    policy_chunks: int
    mode: str
    chroma: str
    documents: dict[str, int] = Field(default_factory=lambda: {"curated": 0, "user_for_caller": 0})
    chunks: dict[str, int] = Field(default_factory=lambda: {"curated": 0, "user_for_caller": 0})
    embedding_backend: str = settings.EMBEDDING_BACKEND
    retrieval: str = "hybrid"
    langgraph_version: str = _LANGGRAPH_VERSION
    graph_compiled: bool = True


class MedicareSuggestionsResponse(BaseModel):
    """Dynamic query suggestions payload generated from live database and index."""

    suggestions: list[str]
    city: str | None = None
    procedure: str | None = None
    insurer: str | None = None


@router.get(
    "/suggestions",
    response_model=MedicareSuggestionsResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def get_medicare_suggestions(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id: str | None = Query(None),
) -> MedicareSuggestionsResponse:
    """Dynamically generate sample question chips from the live database and document index."""
    db_path = settings.MEDICARE_DB_PATH
    city: str | None = None
    procedure: str | None = None
    insurer: str | None = None

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            # Top city
            cursor.execute(
                "SELECT city, COUNT(*) as cnt FROM hospitals WHERE city IS NOT NULL GROUP BY city ORDER BY cnt DESC LIMIT 1;"
            )
            row = cursor.fetchone()
            if row:
                city = row[0]

            # Top procedure
            cursor.execute(
                "SELECT procedure_name, COUNT(*) as cnt FROM hospital_procedures WHERE procedure_name IS NOT NULL GROUP BY procedure_name ORDER BY cnt DESC LIMIT 1;"
            )
            row = cursor.fetchone()
            if row:
                procedure = row[0]

            # Top insurer
            cursor.execute(
                "SELECT insurer_name, COUNT(*) as cnt FROM insurer_acceptance WHERE insurer_name IS NOT NULL GROUP BY insurer_name ORDER BY cnt DESC LIMIT 1;"
            )
            row = cursor.fetchone()
            if row:
                insurer = row[0]
            conn.close()
        except Exception:
            pass

    # If insurer not in DB, inspect manifest
    if not insurer:
        try:
            manifest_repo = get_manifest_repository()
            docs = manifest_repo.list_documents()
            for d in docs:
                if d.insurer:
                    insurer = d.insurer
                    break
        except Exception:
            pass

    resolved_city = city or "your area"
    resolved_procedure = procedure or "elective procedures"
    resolved_insurer = insurer or "standard insurance"

    from medicare.config_loader import get_app_config

    templates = get_app_config().get("suggestion_templates", [])
    suggestions = [
        t.format(procedure=resolved_procedure, city=resolved_city, insurer=resolved_insurer)
        for t in templates
    ]

    return MedicareSuggestionsResponse(
        suggestions=suggestions,
        city=city,
        procedure=procedure,
        insurer=insurer,
    )


@router.get(
    "/status", response_model=MedicareStatusResponse, dependencies=[Depends(verify_bearer_auth)]
)
async def get_medicare_status(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    user_id: str | None = Query(None),
) -> MedicareStatusResponse:
    """Retrieve operational readiness status for hospital SQL database and policy vector store."""
    resolved_user = x_user_id or user_id or "default_user"
    db_path = settings.MEDICARE_DB_PATH
    db_exists = os.path.exists(db_path)
    tables_count: dict[str, int] = {table: 0 for table in sorted(ALLOWED_TABLES)}

    if db_exists:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            for table in ALLOWED_TABLES:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    row = cursor.fetchone()
                    tables_count[table] = row[0] if row else 0
                except sqlite3.OperationalError:
                    tables_count[table] = 0
            conn.close()
        except Exception:
            pass

    # Inspect policy vector store
    policy_tool = PolicySearchTool()
    chroma_status = "fallback" if policy_tool.is_fallback else "ok"
    policy_chunks = 0
    if not policy_tool.is_fallback and policy_tool._collection is not None:
        try:
            policy_chunks = policy_tool._collection.count()
        except Exception:
            policy_chunks = 0

    mode = "mock" if settings.USE_MOCK_MODELS else "live"

    # Query document manifest metrics
    manifest_repo = get_manifest_repository()
    curated_docs = manifest_repo.list_documents(scope="curated")
    user_docs = manifest_repo.list_documents(user_id=resolved_user, scope="user")

    curated_chunks_count = sum(d.chunks for d in curated_docs)
    user_chunks_count = sum(d.chunks for d in user_docs)

    return MedicareStatusResponse(
        db_exists=db_exists,
        tables=tables_count,
        policy_chunks=policy_chunks,
        mode=mode,
        chroma=chroma_status,
        documents={"curated": len(curated_docs), "user_for_caller": len(user_docs)},
        chunks={"curated": curated_chunks_count, "user_for_caller": user_chunks_count},
        embedding_backend=settings.EMBEDDING_BACKEND,
        retrieval="hybrid",
        langgraph_version=_LANGGRAPH_VERSION,
        graph_compiled=True,
    )
