"""Scan test verifying no domain entities or unallowlisted strings exist in ui/."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UI_DIR = REPO_ROOT / "ui"

# Domain entities that must never be hardcoded in UI layer
FORBIDDEN_CITIES = [
    "mumbai",
    "delhi",
    "bangalore",
    "bengaluru",
    "chennai",
    "hyderabad",
    "kolkata",
    "pune",
    "ahmedabad",
]

FORBIDDEN_HOSPITALS = [
    "apollo",
    "fortis",
    "max healthcare",
    "manipal",
    "lilavati",
    "medanta",
    "breach candy",
]

FORBIDDEN_INSURERS = [
    "star health",
    "hdfc ergo",
    "care health",
    "icici lombard",
    "bajaj allianz",
    "niva bupa",
]

FORBIDDEN_PROCEDURES = [
    "cataract",
    "knee replacement",
    "angioplasty",
    "appendectomy",
    "cholecystectomy",
    "hernia repair",
    "hip replacement",
]


def test_ui_has_no_hardcoded_domain_entities():
    """Verify ui/ contains no hardcoded cities, hospitals, insurers, or procedures."""
    all_forbidden = {
        "city": FORBIDDEN_CITIES,
        "hospital": FORBIDDEN_HOSPITALS,
        "insurer": FORBIDDEN_INSURERS,
        "procedure": FORBIDDEN_PROCEDURES,
    }

    violations = []
    for py_file in UI_DIR.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8").lower()
        for category, entities in all_forbidden.items():
            for entity in entities:
                if entity in text:
                    violations.append(
                        f"{py_file.relative_to(REPO_ROOT)}: hardcoded {category} '{entity}'"
                    )

    assert not violations, "Hardcoded domain entities found in UI:\n" + "\n".join(violations)
