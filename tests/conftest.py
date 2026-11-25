"""Shared Pytest fixtures and test harness."""

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medicare.api.app import create_app
from medicare.config import settings
from medicare.storage.checkpointer import InMemoryCheckpointer
from medicare.storage.memory_store import InMemoryMemoryStore

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _snapshot_dir(dir_path: Path) -> dict[str, int]:
    """Capture snapshot of relative paths and sizes in a directory."""
    snapshot: dict[str, int] = {}
    if not dir_path.exists():
        return snapshot
    for root, _, files in os.walk(dir_path):
        for f in files:
            p = Path(root) / f
            try:
                rel = str(p.relative_to(dir_path))
                snapshot[rel] = p.stat().st_size
            except Exception:
                pass
    return snapshot


@pytest.fixture(scope="session", autouse=True)
def isolate_test_runtime_paths() -> Generator[None, None, None]:
    """Autouse session fixture isolating all path settings into a temporary directory.

    Guarantees tests never write into data/ or var/.
    Snapshots data/ and var/ at session start and verifies they remain unchanged.
    """
    data_dir = _REPO_ROOT / "data"
    var_dir = _REPO_ROOT / "var"

    data_start = _snapshot_dir(data_dir)
    var_start = _snapshot_dir(var_dir)

    with tempfile.TemporaryDirectory(prefix="medicare_test_var_") as tmp_var_str:
        tmp_var = Path(tmp_var_str)

        # Copy existing runtime databases and indexes if present in var/
        var_hospitals = var_dir / "hospitals.db"
        if var_hospitals.exists():
            shutil.copy2(var_hospitals, tmp_var / "hospitals.db")

        var_manifest = var_dir / "manifest.db"
        if var_manifest.exists():
            shutil.copy2(var_manifest, tmp_var / "manifest.db")

        var_chroma = var_dir / "chroma"
        if var_chroma.exists():
            shutil.copytree(var_chroma, tmp_var / "chroma")

        # Configure settings to point to isolated temp var
        old_var_dir = getattr(settings, "VAR_DIR", "var")
        old_hospitals_db = settings.MEDICARE_DB_PATH
        old_manifest_db = getattr(settings, "MANIFEST_DB_PATH", "var/manifest.db")
        old_chroma_path = settings.CHROMA_PATH
        old_sqlite_path = settings.SQLITE_PATH
        old_checkpoint_path = settings.LANGGRAPH_CHECKPOINT_PATH
        old_upload_dir = settings.UPLOAD_DIR

        settings.VAR_DIR = str(tmp_var)
        settings.MEDICARE_DB_PATH = str(tmp_var / "hospitals.db")
        settings.MANIFEST_DB_PATH = str(tmp_var / "manifest.db")
        settings.CHROMA_PATH = str(tmp_var / "chroma")
        settings.SQLITE_PATH = str(tmp_var / "platform.db")
        settings.LANGGRAPH_CHECKPOINT_PATH = str(tmp_var / "langgraph_checkpoints.db")
        settings.UPLOAD_DIR = str(tmp_var / "uploads")

        from medicare.rag.store import reset_chroma_store

        reset_chroma_store()

        yield

        reset_chroma_store()

        # Restore settings
        settings.VAR_DIR = old_var_dir
        settings.MEDICARE_DB_PATH = old_hospitals_db
        settings.MANIFEST_DB_PATH = old_manifest_db
        settings.CHROMA_PATH = old_chroma_path
        settings.SQLITE_PATH = old_sqlite_path
        settings.LANGGRAPH_CHECKPOINT_PATH = old_checkpoint_path
        settings.UPLOAD_DIR = old_upload_dir

        # Assert data/ and var/ are unchanged
        data_end = _snapshot_dir(data_dir)
        var_end = _snapshot_dir(var_dir)

        assert data_start == data_end, (
            f"data/ directory was modified during test run! Diff: {set(data_start.items()) ^ set(data_end.items())}"
        )
        assert var_start == var_end, (
            f"var/ directory was modified during test run! Diff: {set(var_start.items()) ^ set(var_end.items())}"
        )


@pytest.fixture(autouse=True)
def enforce_test_mock_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "USE_MOCK_MODELS", True)
    monkeypatch.setattr(settings, "DEFAULT_MODEL", "mock-gpt-4")


@pytest.fixture
def test_checkpointer() -> InMemoryCheckpointer:
    return InMemoryCheckpointer()


@pytest.fixture
def test_memory_store() -> InMemoryMemoryStore:
    return InMemoryMemoryStore()


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    if settings.SERVICE_SECRET_KEY:
        return {"Authorization": f"Bearer {settings.SERVICE_SECRET_KEY}"}
    return {}
