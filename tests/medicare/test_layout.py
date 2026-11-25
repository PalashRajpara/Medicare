"""Test verifying repository layout, database isolation, clean imports, and layering."""

from scripts.verify_layout import (
    verify_clean_imports,
    verify_layering_rules,
    verify_no_db_outside_var,
    verify_no_old_paths,
)


def test_clean_imports():
    """Ensure all modules import cleanly without circular dependencies."""
    errors = verify_clean_imports()
    assert not errors, "Module import errors found:\n" + "\n".join(errors)


def test_layering_rules():
    """Ensure strict architectural import boundaries hold across layers."""
    errors = verify_layering_rules()
    assert not errors, "Layering violations found:\n" + "\n".join(errors)


def test_database_isolation():
    """Ensure no database files exist outside var/."""
    errors = verify_no_db_outside_var()
    assert not errors, "Databases found outside var/:\n" + "\n".join(errors)


def test_no_obsolete_paths():
    """Ensure no obsolete path or module strings remain outside docs/decisions."""
    errors = verify_no_old_paths()
    assert not errors, "Obsolete path references found:\n" + "\n".join(errors)
