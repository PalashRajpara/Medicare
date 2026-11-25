"""CLI Setup Script: Initialize SQLite schema, import CSVs, and index policies."""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from medicare.config import settings
from medicare.medicare.dataset.csv_import import import_csv_directory
from medicare.medicare.dataset.policy_indexer import index_policy_documents
from medicare.medicare.dataset.schema import ALL_DDL_STATEMENTS


def init_database(db_path: str, reset: bool = False) -> None:
    """Create parent dirs and initialize SQLite database schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if reset and path.exists():
        path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        for stmt in ALL_DDL_STATEMENTS:
            conn.executescript(stmt)
        conn.commit()
    finally:
        conn.close()


def get_table_counts(db_path: str) -> dict[str, int]:
    """Return row counts for all tables."""
    if not Path(db_path).exists():
        return {"hospitals": 0, "hospital_procedures": 0, "insurer_acceptance": 0}

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        counts = {}
        for table in ["hospitals", "hospital_procedures", "insurer_acceptance"]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            except Exception:
                counts[table] = 0
        return counts
    finally:
        conn.close()


def init_medicare_database(db_path: str, reset: bool = False) -> None:
    """Alias for init_database."""
    init_database(db_path=db_path, reset=reset)


def main() -> None:
    parser = argparse.ArgumentParser(description="MediCare MediCare & Claim Navigator Setup CLI")
    parser.add_argument("--import-csv", action="store_true", help="Import seed CSVs into SQLite")
    parser.add_argument(
        "--index-policies", action="store_true", help="Chunk and index policy markdown files"
    )
    parser.add_argument(
        "--sync", action="store_true", help="Delete index entries for files removed from disk"
    )
    parser.add_argument(
        "--reindex-all", action="store_true", help="Force reindexing of all policy documents"
    )
    parser.add_argument("--list-docs", action="store_true", help="Print document manifest")
    parser.add_argument(
        "--reset", action="store_true", help="Drop and recreate database and clear vector index"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Confirm reset without interactive prompt"
    )
    parser.add_argument(
        "--all", action="store_true", help="Perform initialization, CSV import, and policy indexing"
    )
    args = parser.parse_args()

    db_path = settings.MEDICARE_DB_PATH
    csv_dir = settings.SEED_CSV_DIR
    policy_dir = settings.POLICY_DOCS_DIR
    chroma_path = settings.CHROMA_PATH
    collection_name = settings.CHROMA_COLLECTION

    if args.list_docs:
        from medicare.rag.manifest import get_manifest_repository

        repo = get_manifest_repository()
        docs = repo.list_documents()
        print(f"\n=== DOCUMENT MANIFEST ({len(docs)} documents) ===")
        for d in docs:
            print(
                f"[{d.scope.upper()}] {d.source} | Insurer: {d.insurer or 'N/A'} | Pages: {d.pages} | Chunks: {d.chunks} | Status: {d.status}"
            )
        return

    if args.reset:
        if not args.yes:
            confirm = input(
                f"Are you sure you want to reset DB ({db_path}) and index ({chroma_path})? [y/N]: "
            )
            if confirm.lower() != "y":
                print("Reset cancelled.")
                sys.exit(0)
        print("Resetting database and vector index...")
        init_database(db_path, reset=True)
        if Path(chroma_path).exists():
            shutil.rmtree(chroma_path)
    else:
        init_database(db_path, reset=False)

    if args.all or args.import_csv:
        print(f"Importing seed CSVs from {csv_dir}...")
        csv_results = import_csv_directory(db_path, csv_dir)
        for fname, stat in csv_results.items():
            print(
                f"  • {fname}: imported={stat.get('imported', 0)}, skipped={stat.get('skipped', 0)}"
            )

    indexed_files = 0
    total_chunks = 0
    if args.all or args.index_policies:
        print(f"Indexing policy documents from {policy_dir}...")
        idx_res = index_policy_documents(
            policy_dir,
            chroma_path,
            collection_name,
            sync=args.sync,
            reindex_all=args.reindex_all,
        )
        indexed_files = idx_res.get("indexed_files", 0)
        total_chunks = idx_res.get("total_chunks", 0)
        print(f"  • Indexed {total_chunks} chunks across {indexed_files} policy files.")

    counts = get_table_counts(db_path)
    abs_db_path = str(Path(db_path).resolve())

    print("\n=== SETUP SUMMARY ===")
    print(f"Database Path: {abs_db_path}")
    print("Table Row Counts:")
    for tbl, count in counts.items():
        print(f"  - {tbl}: {count} rows")
    print(f"Policy Files Indexed: {indexed_files}")
    print(f"Policy Chunks in Index: {total_chunks}")
    print("=====================")


if __name__ == "__main__":
    main()
