"""Test verifying dynamic configuration and absence of raw domain data in source trees."""

import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_no_raw_domain_data_in_source():
    """Fail if any city, hospital, procedure, or insurer name appears in medicare/ or ui/."""
    domain_values: set[str] = set()

    # Collect distinct strings from all seed datasets
    seed_dirs = [
        REPO_ROOT / "data" / "seed",
        REPO_ROOT / "tests" / "fixtures" / "medicare" / "seed",
    ]
    for sdir in seed_dirs:
        if sdir.exists():
            for csv_file in sdir.glob("*.csv"):
                with open(csv_file, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        for col in ("city", "name", "procedure_name", "insurer_name"):
                            if col in row and row[col]:
                                val = row[col].strip()
                                # Only match meaningful tokens length >= 4
                                if len(val) >= 4:
                                    domain_values.add(val.lower())

    assert len(domain_values) > 20, "Domain values set should not be empty."

    # Scan production source directories
    violations: list[str] = []
    source_dirs = [REPO_ROOT / "medicare", REPO_ROOT / "ui"]

    for sdir in source_dirs:
        for py_file in sdir.rglob("*.py"):
            with open(py_file, encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line_lower = line.lower()
                    for val in sorted(domain_values, key=len, reverse=True):
                        # Use word boundary
                        pattern = r"\b" + re.escape(val) + r"\b"
                        if re.search(pattern, line_lower):
                            rel_path = py_file.relative_to(REPO_ROOT)
                            violations.append(
                                f"{rel_path}:{line_no} matches domain value '{val}' -> {line.strip()}"
                            )

    assert not violations, (
        f"Found {len(violations)} raw domain values in production source code:\n"
        + "\n".join(violations[:20])
    )


def test_config_validation_zero_unallowlisted():
    """Run full configuration validation scanner in-process and assert 0 unallowlisted findings."""
    from scripts.validate_config import run_audit

    findings, unallowed = run_audit(REPO_ROOT)
    unallowed_items = [
        f"{f.file}:{f.line} [{f.category}] {f.text}" for f in findings if not f.allowlisted
    ]
    assert unallowed == 0, (
        f"Detected {unallowed} unallowlisted static elements in codebase:\n"
        + "\n".join(unallowed_items[:20])
    )
