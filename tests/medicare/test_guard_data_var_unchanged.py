"""Guard test asserting data/ and var/ directories maintain clean separation."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_data_and_var_contain_only_expected_files():
    """Verify data/ contains only inputs and var/ contains expected runtime state."""
    data_dir = REPO_ROOT / "data"
    var_dir = REPO_ROOT / "var"

    assert data_dir.exists()
    assert (data_dir / "seed").is_dir()
    assert (data_dir / "policies").is_dir()
    assert (data_dir / "README.md").is_file()

    # Ensure no databases or generated caches in data/
    data_files = [f for _, _, files in os.walk(data_dir) for f in files]
    assert not any(f.endswith(".db") for f in data_files)
    assert not any(f.endswith(".sqlite") for f in data_files)
    assert not any(f.endswith(".sqlite3") for f in data_files)

    # Ensure runtime state exists in var/
    assert var_dir.exists()
    assert (var_dir / "hospitals.db").is_file()
    assert (var_dir / "manifest.db").is_file()
    assert (var_dir / "platform.db").is_file()
    assert (var_dir / "chroma").is_dir()
