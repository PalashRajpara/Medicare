"""Test verifying all documentation links and backticked paths exist on disk."""

from scripts.check_docs_links import check_docs_links


def test_documentation_links():
    """Ensure all relative Markdown links and backticked paths resolve to valid files."""
    errors = check_docs_links()
    assert not errors, "Docs link verification failed:\n" + "\n".join(errors)
