"""Database schema, DDL, table/column allowlists, and LLM schema descriptions."""

import re

HOSPITALS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS hospitals (
  hospital_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL,
  rating REAL CHECK (rating BETWEEN 0 AND 5),
  bed_count INTEGER,
  nabh_accredited INTEGER NOT NULL DEFAULT 0 CHECK (nabh_accredited IN (0,1)),
  emergency_wait_minutes INTEGER
);
"""

HOSPITAL_PROCEDURES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS hospital_procedures (
  procedure_id INTEGER PRIMARY KEY,
  hospital_id INTEGER NOT NULL REFERENCES hospitals(hospital_id),
  procedure_name TEXT NOT NULL,
  category TEXT NOT NULL,
  min_cost_inr INTEGER NOT NULL,
  max_cost_inr INTEGER NOT NULL,
  avg_cost_inr INTEGER NOT NULL,
  avg_wait_days INTEGER,
  room_rent_per_day_inr INTEGER,
  CHECK (min_cost_inr <= avg_cost_inr AND avg_cost_inr <= max_cost_inr)
);
"""

INSURER_ACCEPTANCE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS insurer_acceptance (
  acceptance_id INTEGER PRIMARY KEY,
  hospital_id INTEGER NOT NULL REFERENCES hospitals(hospital_id),
  insurer_name TEXT NOT NULL,
  cashless_accepted INTEGER NOT NULL CHECK (cashless_accepted IN (0,1)),
  network_type TEXT,
  avg_claim_settlement_days INTEGER
);
"""

INDEXES_DDL = """
CREATE INDEX IF NOT EXISTS idx_proc_hospital ON hospital_procedures(hospital_id);
CREATE INDEX IF NOT EXISTS idx_proc_name ON hospital_procedures(procedure_name);
CREATE INDEX IF NOT EXISTS idx_hosp_city ON hospitals(city);
CREATE INDEX IF NOT EXISTS idx_ins_hospital ON insurer_acceptance(hospital_id);
CREATE INDEX IF NOT EXISTS idx_ins_name ON insurer_acceptance(insurer_name);
"""

ALL_DDL_STATEMENTS = [
    HOSPITALS_TABLE_DDL,
    HOSPITAL_PROCEDURES_TABLE_DDL,
    INSURER_ACCEPTANCE_TABLE_DDL,
    INDEXES_DDL,
]

ALLOWED_TABLES = {"hospitals", "hospital_procedures", "insurer_acceptance"}

ALLOWED_COLUMNS = {
    "hospitals": {
        "hospital_id",
        "name",
        "city",
        "state",
        "rating",
        "bed_count",
        "nabh_accredited",
        "emergency_wait_minutes",
    },
    "hospital_procedures": {
        "procedure_id",
        "hospital_id",
        "procedure_name",
        "category",
        "min_cost_inr",
        "max_cost_inr",
        "avg_cost_inr",
        "avg_wait_days",
        "room_rent_per_day_inr",
    },
    "insurer_acceptance": {
        "acceptance_id",
        "hospital_id",
        "insurer_name",
        "cashless_accepted",
        "network_type",
        "avg_claim_settlement_days",
    },
}

SCHEMA_DESCRIPTION = """
SQLite Database Schema for MediCare Hospital & Cost Directory:

Table 1: hospitals
- hospital_id (INTEGER PRIMARY KEY): Unique identifier of the hospital.
- name (TEXT NOT NULL): Full legal/trade name of the hospital.
- city (TEXT NOT NULL): City where hospital is located.
- state (TEXT NOT NULL): State or province where hospital is located.
- rating (REAL): Hospital quality rating from 0.0 to 5.0.
- bed_count (INTEGER): Total capacity of inpatient beds.
- nabh_accredited (INTEGER): 1 if National Accreditation Board for Hospitals (NABH) accredited, 0 otherwise.
- emergency_wait_minutes (INTEGER): Estimated typical wait time in emergency room (minutes).

Table 2: hospital_procedures
- procedure_id (INTEGER PRIMARY KEY): Unique identifier for the procedure at this hospital.
- hospital_id (INTEGER NOT NULL): Foreign key referencing hospitals(hospital_id).
- procedure_name (TEXT NOT NULL): Medical treatment/procedure name.
- category (TEXT NOT NULL): Specialty medical category.
- min_cost_inr (INTEGER NOT NULL): Lower bound estimated procedure cost in currency units.
- max_cost_inr (INTEGER NOT NULL): Upper bound estimated procedure cost in currency units.
- avg_cost_inr (INTEGER NOT NULL): Average total cost (min_cost_inr <= avg_cost_inr <= max_cost_inr).
- avg_wait_days (INTEGER): Average waiting time in days before elective admission.
- room_rent_per_day_inr (INTEGER): Standard single-room daily tariff.

Table 3: insurer_acceptance
- acceptance_id (INTEGER PRIMARY KEY): Unique identifier for the hospital-insurer relationship.
- hospital_id (INTEGER NOT NULL): Foreign key referencing hospitals(hospital_id).
- insurer_name (TEXT NOT NULL): Health insurance provider name.
- cashless_accepted (INTEGER NOT NULL): 1 if hospital has cashless agreement, 0 otherwise.
- network_type (TEXT): Network tier classification.
- avg_claim_settlement_days (INTEGER): Average days to settle claims with this insurer.

SQL Construction Rules:
- Always JOIN hospital_procedures and insurer_acceptance to hospitals on hospital_id.
- For city, procedure, or insurer matching, use case-insensitive LIKE: lower(h.city) LIKE lower('%<city>%').
- Select meaningful column aliases: h.name AS hospital_name, hp.avg_cost_inr, hp.min_cost_inr, hp.max_cost_inr, hp.avg_wait_days, ia.cashless_accepted.
- Always include an ORDER BY (e.g., avg_cost_inr ASC or avg_wait_days ASC) and a sensible LIMIT (e.g. LIMIT 15).
""".strip()


def format_schema_for_prompt() -> str:
    """Return formatted database schema text for LLM prompt."""
    return SCHEMA_DESCRIPTION


SQL_SCHEMA_PROMPT = SCHEMA_DESCRIPTION


def validate_sql_query(query: str) -> tuple[bool, str | None]:
    """Perform static safety and allowlist validation on a SQLite query."""
    cleaned = query.strip()
    if not cleaned:
        return False, "Query is empty."

    # Strip single trailing semicolon
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    # Reject stacked / multiple queries
    if ";" in cleaned:
        return (
            False,
            "Multiple stacked statements are forbidden. Only a single SELECT query is permitted.",
        )

    # Must start with SELECT or WITH
    tokens = cleaned.split()
    first_token = tokens[0].upper() if tokens else ""
    if first_token not in ("SELECT", "WITH"):
        return (
            False,
            f"Forbidden statement type '{first_token}'. Only SELECT statements are allowed.",
        )

    # Forbidden DML/DDL or master table access
    forbidden_patterns = [
        (r"\bdrop\b", "DROP statement is strictly forbidden."),
        (r"\bdelete\b", "DELETE statement is strictly forbidden."),
        (r"\binsert\b", "INSERT statement is strictly forbidden."),
        (r"\bupdate\b", "UPDATE statement is strictly forbidden."),
        (r"\balter\b", "ALTER statement is strictly forbidden."),
        (r"\battach\b", "ATTACH DATABASE statement is forbidden."),
        (r"\bpragma\b", "PRAGMA statement is forbidden."),
        (r"\bsqlite_master\b", "Access to sqlite_master is forbidden."),
    ]
    for pattern, reason in forbidden_patterns:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return False, reason

    return True, None
