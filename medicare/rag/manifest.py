"""SQLite manifest repository tracking indexed documents and processing status."""

import os
import sqlite3
from typing import Any

from medicare.config import settings
from medicare.rag.models import DocumentRecord

DEFAULT_MANIFEST_DB = getattr(settings, "MANIFEST_DB_PATH", "var/manifest.db")


class ManifestRepository:
    """Manages document metadata, scopes, and processing status in SQLite."""

    def __init__(self, db_path: str = DEFAULT_MANIFEST_DB) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_manifest (
                    doc_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    user_id TEXT,
                    path TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    insurer TEXT,
                    doc_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    pages INTEGER NOT NULL,
                    chunks INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_manifest_user_id ON document_manifest (user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_manifest_scope ON document_manifest (scope)"
            )
            conn.commit()

    def upsert_document(self, doc: DocumentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO document_manifest
                (doc_id, scope, user_id, path, source, title, insurer, doc_type, sha256, pages, chunks, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    scope=excluded.scope,
                    user_id=excluded.user_id,
                    path=excluded.path,
                    source=excluded.source,
                    title=excluded.title,
                    insurer=excluded.insurer,
                    doc_type=excluded.doc_type,
                    sha256=excluded.sha256,
                    pages=excluded.pages,
                    chunks=excluded.chunks,
                    status=excluded.status,
                    error=excluded.error,
                    created_at=excluded.created_at
                """,
                (
                    doc.doc_id,
                    doc.scope,
                    doc.user_id,
                    doc.path,
                    doc.source,
                    doc.title,
                    doc.insurer,
                    doc.doc_type,
                    doc.sha256,
                    doc.pages,
                    doc.chunks,
                    doc.status,
                    doc.error,
                    doc.created_at,
                ),
            )
            conn.commit()

    def get_document(self, doc_id: str) -> DocumentRecord | None:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM document_manifest WHERE doc_id = ?", (doc_id,))
            row = cur.fetchone()
            if not row:
                return None
            return DocumentRecord(**dict(row))

    def list_documents(
        self, user_id: str | None = None, scope: str | None = None
    ) -> list[DocumentRecord]:
        query = "SELECT * FROM document_manifest WHERE 1=1"
        params: list[Any] = []
        if scope:
            query += " AND scope = ?"
            params.append(scope)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)

        query += " ORDER BY created_at DESC"
        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [DocumentRecord(**dict(row)) for row in cur.fetchall()]

    def delete_document(self, doc_id: str, user_id: str | None = None) -> bool:
        with self._get_connection() as conn:
            if user_id:
                cur = conn.execute(
                    "DELETE FROM document_manifest WHERE doc_id = ? AND user_id = ?",
                    (doc_id, user_id),
                )
            else:
                cur = conn.execute("DELETE FROM document_manifest WHERE doc_id = ?", (doc_id,))
            conn.commit()
            return cur.rowcount > 0


_manifest_repo: ManifestRepository | None = None


def get_manifest_repository(db_path: str | None = None) -> ManifestRepository:
    global _manifest_repo
    target_db = db_path or getattr(settings, "MANIFEST_DB_PATH", "var/manifest.db")
    if _manifest_repo is None or _manifest_repo.db_path != target_db:
        _manifest_repo = ManifestRepository(target_db)
    return _manifest_repo
