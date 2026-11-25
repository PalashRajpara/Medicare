"""OpenAPI regression test verifying endpoints and schemas match baseline."""

import json
from pathlib import Path

from medicare.api.app import create_app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_openapi_schema_regression():
    """Ensure current OpenAPI schema maintains exact path compatibility with baseline."""
    baseline_path = FIXTURES_DIR / "openapi_baseline.json"
    assert baseline_path.exists(), f"Baseline OpenAPI fixture not found at {baseline_path}"

    baseline_openapi = json.loads(baseline_path.read_text(encoding="utf-8"))
    app = create_app()
    current_openapi = app.openapi()

    baseline_paths = set(baseline_openapi.get("paths", {}).keys())
    current_paths = set(current_openapi.get("paths", {}).keys())

    missing_paths = baseline_paths - current_paths
    assert not missing_paths, f"Missing OpenAPI endpoints: {missing_paths}"

    # Verify each endpoint has the same operations
    for path in baseline_paths:
        base_ops = set(baseline_openapi["paths"][path].keys())
        curr_ops = set(current_openapi["paths"][path].keys())
        assert base_ops == curr_ops, (
            f"Operations mismatch for {path}: expected {base_ops}, got {curr_ops}"
        )
