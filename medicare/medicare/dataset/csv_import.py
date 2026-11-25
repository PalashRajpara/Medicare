"""CSV validation and ingestion into SQLite database."""

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EXPECTED_HEADERS = {
    "hospitals.csv": [
        "hospital_id",
        "name",
        "city",
        "state",
        "rating",
        "bed_count",
        "nabh_accredited",
        "emergency_wait_minutes",
    ],
    "hospital_procedures.csv": [
        "procedure_id",
        "hospital_id",
        "procedure_name",
        "category",
        "min_cost_inr",
        "max_cost_inr",
        "avg_cost_inr",
        "avg_wait_days",
        "room_rent_per_day_inr",
    ],
    "insurer_acceptance.csv": [
        "acceptance_id",
        "hospital_id",
        "insurer_name",
        "cashless_accepted",
        "network_type",
        "avg_claim_settlement_days",
    ],
}


def _validate_hospital_row(
    row: dict[str, str], row_num: int
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        hospital_id = int(row["hospital_id"])
        name = row["name"].strip()
        city = row["city"].strip()
        state = row["state"].strip()
        if not name or not city or not state:
            return None, f"Row {row_num}: name, city, and state cannot be empty"

        rating = float(row["rating"]) if row.get("rating") else None
        if rating is not None and not (0.0 <= rating <= 5.0):
            return None, f"Row {row_num}: rating {rating} must be between 0.0 and 5.0"

        bed_count = int(row["bed_count"]) if row.get("bed_count") else None
        nabh = int(row.get("nabh_accredited", 0))
        if nabh not in (0, 1):
            return None, f"Row {row_num}: nabh_accredited must be 0 or 1"

        emergency_wait = (
            int(row["emergency_wait_minutes"]) if row.get("emergency_wait_minutes") else None
        )

        return {
            "hospital_id": hospital_id,
            "name": name,
            "city": city,
            "state": state,
            "rating": rating,
            "bed_count": bed_count,
            "nabh_accredited": nabh,
            "emergency_wait_minutes": emergency_wait,
        }, None
    except Exception as e:
        return None, f"Row {row_num}: invalid type ({e})"


def _validate_procedure_row(
    row: dict[str, str], row_num: int, valid_hospital_ids: set[int]
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        procedure_id = int(row["procedure_id"])
        hospital_id = int(row["hospital_id"])
        if hospital_id not in valid_hospital_ids:
            return (
                None,
                f"Row {row_num}: hospital_id {hospital_id} invalid",
            )

        procedure_name = row["procedure_name"].strip()
        category = row["category"].strip()
        if not procedure_name or not category:
            return None, f"Row {row_num}: empty procedure or category"

        min_cost = int(row["min_cost_inr"])
        max_cost = int(row["max_cost_inr"])
        avg_cost = int(row["avg_cost_inr"])
        if not (min_cost <= avg_cost <= max_cost):
            return (
                None,
                f"Row {row_num}: cost constraint violated",
            )

        avg_wait = int(row["avg_wait_days"]) if row.get("avg_wait_days") else None
        room_rent = int(row["room_rent_per_day_inr"]) if row.get("room_rent_per_day_inr") else None

        return {
            "procedure_id": procedure_id,
            "hospital_id": hospital_id,
            "procedure_name": procedure_name,
            "category": category,
            "min_cost_inr": min_cost,
            "max_cost_inr": max_cost,
            "avg_cost_inr": avg_cost,
            "avg_wait_days": avg_wait,
            "room_rent_per_day_inr": room_rent,
        }, None
    except Exception as e:
        return None, f"Row {row_num}: invalid type ({e})"


def _validate_acceptance_row(
    row: dict[str, str], row_num: int, valid_hospital_ids: set[int]
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        acceptance_id = int(row["acceptance_id"])
        hospital_id = int(row["hospital_id"])
        if hospital_id not in valid_hospital_ids:
            return (
                None,
                f"Row {row_num}: hospital_id {hospital_id} invalid",
            )

        insurer_name = row["insurer_name"].strip()
        if not insurer_name:
            return None, f"Row {row_num}: insurer_name cannot be empty"

        cashless = int(row["cashless_accepted"])
        if cashless not in (0, 1):
            return None, f"Row {row_num}: invalid acceptance flag"

        network_type = row.get("network_type", "").strip() or None
        avg_settlement = (
            int(row["avg_claim_settlement_days"]) if row.get("avg_claim_settlement_days") else None
        )

        return {
            "acceptance_id": acceptance_id,
            "hospital_id": hospital_id,
            "insurer_name": insurer_name,
            "cashless_accepted": cashless,
            "network_type": network_type,
            "avg_claim_settlement_days": avg_settlement,
        }, None
    except Exception as e:
        return None, f"Row {row_num}: invalid type ({e})"


def import_csv_directory(db_path: str, csv_dir: str) -> dict[str, Any]:
    ...
    """Import hospitals.csv, hospital_procedures.csv, and insurer_acceptance.csv into SQLite."""
    dir_path = Path(csv_dir)
    results: dict[str, Any] = {}

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        # Track valid hospital IDs for foreign key validation
        cursor = conn.cursor()
        cursor.execute("SELECT hospital_id FROM hospitals")
        valid_hospital_ids = {row[0] for row in cursor.fetchall()}

        # 1. Import hospitals.csv first
        hosp_file = dir_path / "hospitals.csv"
        if hosp_file.exists():
            res = _import_single_file(
                conn, hosp_file, "hospitals", _validate_hospital_row, valid_hospital_ids
            )
            results["hospitals.csv"] = res
            # Refresh valid hospital IDs
            cursor.execute("SELECT hospital_id FROM hospitals")
            valid_hospital_ids = {row[0] for row in cursor.fetchall()}
        else:
            results["hospitals.csv"] = {"status": "missing", "imported": 0}
            logger.warning(f"File missing: {hosp_file}")

        # 2. Import hospital_procedures.csv
        proc_file = dir_path / "hospital_procedures.csv"
        if proc_file.exists():
            res = _import_single_file(
                conn, proc_file, "hospital_procedures", _validate_procedure_row, valid_hospital_ids
            )
            results["hospital_procedures.csv"] = res
        else:
            results["hospital_procedures.csv"] = {"status": "missing", "imported": 0}
            logger.warning(f"File missing: {proc_file}")

        # 3. Import insurer_acceptance.csv
        ins_file = dir_path / "insurer_acceptance.csv"
        if ins_file.exists():
            res = _import_single_file(
                conn, ins_file, "insurer_acceptance", _validate_acceptance_row, valid_hospital_ids
            )
            results["insurer_acceptance.csv"] = res
        else:
            results["insurer_acceptance.csv"] = {"status": "missing", "imported": 0}
            logger.warning(f"File missing: {ins_file}")

        conn.commit()
    finally:
        conn.close()

    return results


def _import_single_file(
    conn: sqlite3.Connection,
    file_path: Path,
    table_name: str,
    validator_func: Any,
    valid_hospital_ids: set[int],
) -> dict[str, Any]:
    file_name = file_path.name
    expected_header = EXPECTED_HEADERS.get(file_name, [])
    errors: list[str] = []
    imported_count = 0
    skipped_count = 0

    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {"status": "empty", "imported": 0, "errors": ["File has no headers"]}

        # Check headers
        normalized_headers = [h.strip() for h in reader.fieldnames]
        if normalized_headers != expected_header:
            return {
                "status": "header_mismatch",
                "imported": 0,
                "errors": [f"Expected headers {expected_header}, got {normalized_headers}"],
            }

        rows_to_insert = []
        for idx, row in enumerate(reader, start=2):
            if table_name == "hospitals":
                val, err = validator_func(row, idx)
            else:
                val, err = validator_func(row, idx, valid_hospital_ids)

            if err:
                errors.append(err)
                skipped_count += 1
            elif val:
                rows_to_insert.append(val)

        if rows_to_insert:
            columns = list(rows_to_insert[0].keys())
            placeholders = ", ".join([f":{col}" for col in columns])
            col_names = ", ".join(columns)
            sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"
            conn.executemany(sql, rows_to_insert)
            imported_count = len(rows_to_insert)

    return {
        "status": "ok",
        "imported": imported_count,
        "skipped": skipped_count,
        "errors": errors,
    }


def import_all_csvs(seed_dir: str, db_path: str) -> dict[str, Any]:
    """Convenience wrapper for importing all seed CSVs returning table name -> imported row count."""
    res = import_csv_directory(db_path=db_path, csv_dir=seed_dir)
    return {
        "hospitals": res.get("hospitals.csv", {}).get("imported", 0),
        "hospital_procedures": res.get("hospital_procedures.csv", {}).get("imported", 0),
        "insurer_acceptance": res.get("insurer_acceptance.csv", {}).get("imported", 0),
    }


def import_csv_to_table(csv_path: str, table_name: str, db_path: str) -> tuple[int, int]:
    """Import a single CSV file returning (imported_count, skipped_count)."""
    validators = {
        "hospitals": _validate_hospital_row,
        "hospital_procedures": _validate_procedure_row,
        "insurer_acceptance": _validate_acceptance_row,
    }
    with sqlite3.connect(db_path) as conn:
        valid_hospital_ids: set[int] = set()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT hospital_id FROM hospitals")
            valid_hospital_ids = {row[0] for row in cursor.fetchall()}
        except Exception:
            pass
        res = _import_single_file(
            conn, Path(csv_path), table_name, validators[table_name], valid_hospital_ids
        )
        conn.commit()
    return res.get("imported", 0), res.get("skipped", 0)
