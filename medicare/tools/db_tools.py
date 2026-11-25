"""Dynamic database and document index discovery tools with exposure control and caching."""

import csv
import difflib
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from medicare.config import settings
from medicare.rag.manifest import get_manifest_repository
from medicare.tools.base import BaseTool

logger = logging.getLogger(__name__)


def _resolve_exposure_config() -> dict[str, Any]:
    """Load medicare exposure allowlist/denylist from config."""
    config_dir = getattr(settings, "CONFIG_DIR", "config")
    p = Path(config_dir) / "medicare_exposure.yaml"
    if not p.exists():
        p = Path(__file__).resolve().parent.parent.parent / "config" / "medicare_exposure.yaml"
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load medicare_exposure.yaml (%s)", e)
    return {
        "hidden_tables": ["sqlite_sequence", "sqlite_stat1"],
        "hidden_columns": ["created_at", "updated_at", "password_hash", "internal_notes"],
    }


_EXPOSURE = _resolve_exposure_config()
HIDDEN_TABLES: set[str] = set(_EXPOSURE.get("hidden_tables", []))
HIDDEN_COLUMNS: set[str] = set(_EXPOSURE.get("hidden_columns", []))


# Schema Cache: (db_path, mtime) -> schema_dict
_SCHEMA_CACHE: dict[str, Any] = {}
_LAST_MTIME: dict[str, float] = {}


def get_known_catalog(
    db_path: str | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Dynamically discover distinct cities, procedures, and insurers from live DB or seed CSVs."""
    if db_path is None:
        try:
            from medicare.tools.sql_query import SQLiteQueryTool

            target_db = SQLiteQueryTool.ACTIVE_DB_PATH or settings.MEDICARE_DB_PATH
        except Exception:
            target_db = settings.MEDICARE_DB_PATH
    else:
        target_db = db_path
    cities_map: dict[str, str] = {}
    procedures_map: dict[str, str] = {}
    insurers_map: dict[str, str] = {}

    # 1. Inspect live SQLite DB if available
    if os.path.exists(target_db):
        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT city FROM hospitals WHERE city IS NOT NULL")
            for r in cur.fetchall():
                if r[0]:
                    cities_map[str(r[0]).strip().lower()] = str(r[0]).strip()

            cur.execute(
                "SELECT DISTINCT procedure_name FROM hospital_procedures WHERE procedure_name IS NOT NULL"
            )
            for r in cur.fetchall():
                if r[0]:
                    raw_p = str(r[0]).strip()
                    procedures_map[raw_p.lower()] = raw_p
                    clean_p = re.sub(r"\s*\(.*?\)", "", raw_p).strip()
                    if clean_p:
                        procedures_map[clean_p.lower()] = clean_p
                        base_p = re.sub(
                            r"^(Total|Laparoscopic|Permanent|Normal|Laser)\s+",
                            "",
                            clean_p,
                            flags=re.I,
                        ).strip()
                        if base_p:
                            procedures_map[base_p.lower()] = base_p

            cur.execute(
                "SELECT DISTINCT insurer_name FROM insurer_acceptance WHERE insurer_name IS NOT NULL"
            )
            for r in cur.fetchall():
                if r[0]:
                    raw_ins = str(r[0]).strip()
                    insurers_map[raw_ins.lower()] = raw_ins
                    clean_ins = re.sub(
                        r"(?i)\s+(General Insurance|and Allied Insurance|Health Insurance|Assurance|Insurance|Care)\b.*",
                        "",
                        raw_ins,
                    ).strip()
                    if clean_ins:
                        insurers_map[clean_ins.lower()] = clean_ins.title()
            conn.close()
        except Exception:
            pass

    # 2. Inspect seed CSVs (data/seed and tests/fixtures/medicare/seed)
    seed_dirs = [
        Path(getattr(settings, "SEED_CSV_DIR", "data/seed")),
        Path("tests/fixtures/medicare/seed"),
    ]
    for sdir in seed_dirs:
        # Hospitals CSV for cities
        h_csv = sdir / "hospitals.csv"
        if h_csv.exists():
            try:
                with open(h_csv, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        c = row.get("city")
                        if c and c.strip():
                            cities_map[c.strip().lower()] = c.strip()
            except Exception:
                pass

        # Procedures CSV
        p_csv = sdir / "hospital_procedures.csv"
        if p_csv.exists():
            try:
                with open(p_csv, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        p = row.get("procedure_name")
                        if p and p.strip():
                            raw_p = p.strip()
                            procedures_map[raw_p.lower()] = raw_p
                            clean_p = re.sub(r"\s*\(.*?\)", "", raw_p).strip()
                            if clean_p:
                                procedures_map[clean_p.lower()] = clean_p
                                base_p = re.sub(
                                    r"^(Total|Laparoscopic|Permanent|Normal|Laser)\s+",
                                    "",
                                    clean_p,
                                    flags=re.I,
                                ).strip()
                                if base_p:
                                    procedures_map[base_p.lower()] = base_p
            except Exception:
                pass

        # Insurers CSV
        i_csv = sdir / "insurer_acceptance.csv"
        if i_csv.exists():
            try:
                with open(i_csv, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        ins = row.get("insurer_name")
                        if ins and ins.strip():
                            raw_ins = ins.strip()
                            insurers_map[raw_ins.lower()] = raw_ins
                            clean_ins = re.sub(
                                r"(?i)\s+(General Insurance|and Allied Insurance|Health Insurance|Assurance|Insurance|Care)\b.*",
                                "",
                                raw_ins,
                            ).strip()
                            if clean_ins:
                                insurers_map[clean_ins.lower()] = clean_ins.title()
            except Exception:
                pass

    return cities_map, procedures_map, insurers_map


def get_live_schema(db_path: str | None = None) -> dict[str, Any]:
    """Introspect tables, columns, foreign keys, and sample rows from the live database.

    Automatically refreshes when the database file mtime changes.
    Filters out hidden tables and hidden columns.
    """
    target_db = db_path or settings.MEDICARE_DB_PATH
    if not os.path.exists(target_db):
        return {"tables": {}, "exposed_tables": [], "exposed_columns": {}}

    try:
        current_mtime = os.path.getmtime(target_db)
    except OSError:
        current_mtime = 0.0

    if target_db in _SCHEMA_CACHE and _LAST_MTIME.get(target_db) == current_mtime:
        return _SCHEMA_CACHE[target_db]

    schema_info: dict[str, Any] = {
        "tables": {},
        "exposed_tables": [],
        "exposed_columns": {},
    }

    try:
        conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Find all user tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        table_names = [r[0] for r in cursor.fetchall() if r[0] not in HIDDEN_TABLES]

        for table in table_names:
            cursor.execute(f"PRAGMA table_info({table});")
            col_rows = cursor.fetchall()

            columns = []
            allowed_cols = set()
            for cr in col_rows:
                col_name = cr["name"]
                # Check column exposure
                full_col_name = f"{table}.{col_name}"
                if col_name in HIDDEN_COLUMNS or full_col_name in HIDDEN_COLUMNS:
                    continue

                allowed_cols.add(col_name)
                columns.append(
                    {
                        "name": col_name,
                        "type": cr["type"],
                        "notnull": bool(cr["notnull"]),
                        "pk": bool(cr["pk"]),
                    }
                )

            # Foreign keys
            cursor.execute(f"PRAGMA foreign_key_list({table});")
            fk_rows = cursor.fetchall()
            foreign_keys = [
                {
                    "from": fk["from"],
                    "to_table": fk["table"],
                    "to_column": fk["to"],
                }
                for fk in fk_rows
                if fk["table"] not in HIDDEN_TABLES
            ]

            # Sample rows (up to 3)
            sample_rows = []
            if allowed_cols:
                col_select = ", ".join(f'"{c}"' for c in sorted(allowed_cols))
                try:
                    cursor.execute(f"SELECT {col_select} FROM {table} LIMIT 3;")
                    for srow in cursor.fetchall():
                        sample_rows.append(dict(srow))
                except Exception:
                    pass

            schema_info["tables"][table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "sample_rows": sample_rows,
            }
            schema_info["exposed_tables"].append(table)
            schema_info["exposed_columns"][table] = allowed_cols

        conn.close()
        _SCHEMA_CACHE[target_db] = schema_info
        _LAST_MTIME[target_db] = current_mtime
    except Exception as e:
        logger.warning("Error introspecting live schema (%s)", e)

    return schema_info


def format_schema_documentation(schema_info: dict[str, Any]) -> str:
    """Format live schema dictionary into clean readable documentation for LLMs."""
    if not schema_info or not schema_info.get("tables"):
        return "Database schema is empty or database file is not initialized."

    lines = ["LIVE DATABASE SCHEMA:"]
    for table_name, t_meta in sorted(schema_info["tables"].items()):
        cols = t_meta.get("columns", [])
        col_strs = [f"{c['name']} ({c['type']}{', PK' if c['pk'] else ''})" for c in cols]
        lines.append(f"\nTable: {table_name}")
        lines.append(f"  Columns: {', '.join(col_strs)}")

        fks = t_meta.get("foreign_keys", [])
        if fks:
            fk_strs = [f"{fk['from']} -> {fk['to_table']}({fk['to_column']})" for fk in fks]
            lines.append(f"  Foreign Keys: {', '.join(fk_strs)}")

        samples = t_meta.get("sample_rows", [])
        if samples:
            lines.append(f"  Sample Rows ({len(samples)}):")
            for r in samples:
                lines.append(f"    {r}")

    return "\n".join(lines)


class GetSchemaTool(BaseTool):
    """Tool to inspect the live database schema, types, foreign keys, and sample records."""

    name = "get_schema"
    description = (
        "Inspect the live database schema. Returns tables, columns, data types, "
        "foreign keys, and 3 sample rows for each exposed table."
    )

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path

    async def execute(self, **kwargs: Any) -> str:
        schema = get_live_schema(self.db_path)
        return format_schema_documentation(schema)

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }


class LookupValuesTool(BaseTool):
    """Tool to search and resolve exact stored values (cities, procedures, insurers, hospitals)."""

    name = "lookup_values"
    description = (
        "Search exact stored database values in a given table and column using substring "
        "and fuzzy matching. Returns exact spellings for cities, procedures, insurers, or hospitals."
    )

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path

    async def execute(self, table: str, column: str, text: str, limit: int = 8) -> str:
        target_db = self.db_path or settings.MEDICARE_DB_PATH
        if not os.path.exists(target_db):
            return "[]"

        # Check exposure allowlist
        schema = get_live_schema(target_db)
        exposed_cols = schema.get("exposed_columns", {}).get(table, set())
        if column not in exposed_cols:
            return (
                f"Error: Column '{column}' on table '{table}' is either hidden or does not exist. "
                f"Exposed columns for '{table}': {sorted(list(exposed_cols))}"
            )

        try:
            conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL;'
            )
            raw_values = [str(r[0]) for r in cursor.fetchall() if r[0] is not None]
            conn.close()

            text_clean = text.strip()
            text_lower = text_clean.lower()

            # 1. Exact case-insensitive match
            exact_matches = [v for v in raw_values if v.lower() == text_lower]

            # 2. Substring matches
            substring_matches = [
                v for v in raw_values if text_lower in v.lower() and v not in exact_matches
            ]

            # 3. Fuzzy matches
            fuzzy_matches = [
                v
                for v in difflib.get_close_matches(text_clean, raw_values, n=limit, cutoff=0.55)
                if v not in exact_matches and v not in substring_matches
            ]

            combined = exact_matches + substring_matches + fuzzy_matches
            results = combined[:limit]

            import json

            return json.dumps(results)
        except Exception as e:
            return f"Error looking up values: {e}"

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "description": "Database table name (e.g. hospitals, hospital_procedures, insurer_acceptance)",
                        },
                        "column": {
                            "type": "string",
                            "description": "Column name to search (e.g. city, procedure_name, insurer_name, name)",
                        },
                        "text": {
                            "type": "string",
                            "description": "Text query or partial entity name to search for",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default 8)",
                            "default": 8,
                        },
                    },
                    "required": ["table", "column", "text"],
                },
            },
        }


class ListDocumentFiltersTool(BaseTool):
    """Tool to discover available insurers and document categories in the active index."""

    name = "list_document_filters"
    description = (
        "Discover insurers and document types currently present in the policy document index."
    )

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path

    async def execute(self, **kwargs: Any) -> str:
        insurers: set[str] = set()
        doc_types: set[str] = set()

        # 1. Inspect manifest repository
        try:
            manifest_repo = get_manifest_repository()
            docs = manifest_repo.list_documents()
            for doc in docs:
                if doc.insurer:
                    insurers.add(doc.insurer)
                if doc.doc_type:
                    doc_types.add(doc.doc_type)
        except Exception:
            pass

        # 2. Also check database insurer_acceptance if available
        target_db = self.db_path or settings.MEDICARE_DB_PATH
        if os.path.exists(target_db):
            try:
                conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT insurer_name FROM insurer_acceptance WHERE insurer_name IS NOT NULL;"
                )
                for r in cursor.fetchall():
                    if r[0]:
                        insurers.add(r[0])
                conn.close()
            except Exception:
                pass

        import json

        return json.dumps(
            {
                "insurers": sorted(list(insurers)),
                "document_types": sorted(list(doc_types)),
            }
        )

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }


class SearchDocumentsTool(BaseTool):
    """Tool to search insurance policy terms, waiting periods, exclusions, and claim guidelines."""

    name = "search_documents"
    description = (
        "Search health insurance policy documents, waiting periods, pre-existing condition "
        "rules, cashless guidelines, and claim terms."
    )

    def __init__(self, policy_tool: Any = None) -> None:
        self.policy_tool = policy_tool

    async def execute(
        self,
        query: str,
        insurer: str | None = None,
        scope: str = "both",
    ) -> str:
        from medicare.tools.policy_search import PolicySearchTool

        tool = self.policy_tool or PolicySearchTool()
        citations = tool.search(
            query=query,
            insurer=insurer,
            doc_scope=scope,
            top_k=settings.RAG_TOP_K,
        )

        if not citations:
            return "No matching policy documents or clauses found."

        import json

        results = []
        for idx, c in enumerate(citations, start=1):
            cite_id = c.cite_id or f"C{idx}"
            results.append(
                {
                    "citation_id": cite_id,
                    "section": c.section,
                    "source": c.source,
                    "page": c.page,
                    "score": round(c.score, 4),
                    "text": c.text,
                }
            )
        return json.dumps(results, indent=2)

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query for policy clauses (e.g. '<procedure> waiting period', 'copay rules')",
                        },
                        "insurer": {
                            "type": "string",
                            "description": "Optional insurer name to filter search",
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["curated", "mine", "both"],
                            "description": "Document scope",
                            "default": "both",
                        },
                    },
                    "required": ["query"],
                },
            },
        }
