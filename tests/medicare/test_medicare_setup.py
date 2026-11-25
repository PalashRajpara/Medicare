"""Tests for database setup, schema migration, CSV import validation, and policy chunking."""

import os
import sqlite3

from medicare.medicare.dataset.cli import init_medicare_database
from medicare.medicare.dataset.csv_import import import_all_csvs, import_csv_to_table
from medicare.medicare.dataset.policy_indexer import chunk_markdown_file


def test_init_database_idempotent(tmp_path):
    db_file = str(tmp_path / "init_test.db")
    # First init
    init_medicare_database(db_path=db_file)
    assert os.path.exists(db_file)

    # Second init (must not fail)
    init_medicare_database(db_path=db_file)
    conn = sqlite3.connect(db_file)
    tables = [
        row[0]
        for row in conn.cursor()
        .execute("SELECT name FROM sqlite_master WHERE type='table'")
        .fetchall()
    ]
    conn.close()
    assert "hospitals" in tables
    assert "hospital_procedures" in tables
    assert "insurer_acceptance" in tables


def test_csv_import_with_validation_and_idempotence(tmp_path):
    db_file = str(tmp_path / "csv_test.db")
    init_medicare_database(db_path=db_file)

    seed_dir = "tests/fixtures/medicare/seed"
    # First import
    counts1 = import_all_csvs(seed_dir=seed_dir, db_path=db_file)
    assert counts1["hospitals"] == 3
    assert counts1["hospital_procedures"] == 10
    assert counts1["insurer_acceptance"] == 6

    # Re-import should be idempotent (INSERT OR REPLACE)
    counts2 = import_all_csvs(seed_dir=seed_dir, db_path=db_file)
    assert counts2["hospitals"] == 3

    conn = sqlite3.connect(db_file)
    hosp_count = conn.cursor().execute("SELECT COUNT(*) FROM hospitals").fetchone()[0]
    conn.close()
    assert hosp_count == 3


def test_csv_import_skips_invalid_rows(tmp_path):
    db_file = str(tmp_path / "bad_csv.db")
    init_medicare_database(db_path=db_file)

    # Create CSV with 1 good row and 1 invalid row (rating > 5)
    bad_csv = tmp_path / "hospitals.csv"
    bad_csv.write_text(
        "hospital_id,name,city,state,rating,bed_count,nabh_accredited,emergency_wait_minutes\n"
        "10,Good Hospital,Surat,Gujarat,4.5,100,1,10\n"
        "11,Bad Hospital,Surat,Gujarat,9.5,100,1,10\n"
    )

    imported, skipped = import_csv_to_table(str(bad_csv), "hospitals", db_file)
    assert imported == 1
    assert skipped == 1


def test_policy_markdown_chunking():
    fixture_doc = "tests/fixtures/medicare/policies/star_health_comprehensive.md"
    chunks = chunk_markdown_file(fixture_doc)
    assert len(chunks) >= 5
    for c in chunks:
        assert c.source == "star_health_comprehensive.md"
        assert c.section != ""
        assert len(c.text) > 0


def test_empty_folders_handled_cleanly(tmp_path):
    empty_seed = str(tmp_path / "empty_seed")
    os.makedirs(empty_seed, exist_ok=True)
    db_file = str(tmp_path / "empty_db.db")
    init_medicare_database(db_path=db_file)

    counts = import_all_csvs(seed_dir=empty_seed, db_path=db_file)
    assert all(count == 0 for count in counts.values())
