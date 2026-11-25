"""Tests for /documents multi-format upload, status, list, and delete REST APIs."""

import pytest
from fastapi.testclient import TestClient

from medicare.api.app import create_app


@pytest.fixture
def api_client():
    app = create_app()
    return TestClient(app)


def test_upload_valid_markdown_document(api_client: TestClient):
    """Verify POST /documents accepts valid Markdown file, indexes it, and returns 202/ready."""
    md_bytes = b"# Test Health Policy\n\nRoom rent is capped at 1% of sum insured.\n"
    files = {"file": ("test_policy.md", md_bytes, "text/markdown")}
    headers = {"X-User-Id": "user_doc_test_1"}

    resp = api_client.post(
        "/documents",
        data={"insurer": "Care Health", "doc_type": "policy"},
        files=files,
        headers=headers,
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] in ("ready", "processing")
    doc_id = data["doc_id"]

    # Check GET /documents/{id}
    status_resp = api_client.get(f"/documents/{doc_id}", headers=headers)
    assert status_resp.status_code == 200
    doc_data = status_resp.json()
    assert doc_data["doc_id"] == doc_id
    assert doc_data["filename"] == "test_policy.md"
    assert doc_data["chunks"] >= 1


def test_reject_unsupported_file_extension(api_client: TestClient):
    """Verify POST /documents rejects unsupported file extensions."""
    exe_bytes = b"MZ executable binary payload"
    files = {"file": ("malware.exe", exe_bytes, "application/octet-stream")}
    headers = {"X-User-Id": "user_doc_test_2"}

    resp = api_client.post("/documents", files=files, headers=headers)
    assert resp.status_code == 400
    assert "Unsupported file extension" in resp.json().get("detail", "")


def test_get_document_returns_404_for_other_user(api_client: TestClient):
    """Verify GET /documents/{id} returns 404 when requested by a different user."""
    txt_bytes = b"Private health note\n"
    files = {"file": ("private.txt", txt_bytes, "text/plain")}
    headers_owner = {"X-User-Id": "user_owner"}
    headers_other = {"X-User-Id": "user_other"}

    upload_resp = api_client.post("/documents", files=files, headers=headers_owner)
    assert upload_resp.status_code == 202
    doc_id = upload_resp.json()["doc_id"]

    # Other user attempts to access document
    forbidden_resp = api_client.get(f"/documents/{doc_id}", headers=headers_other)
    assert forbidden_resp.status_code == 404


def test_delete_document_owner_only(api_client: TestClient):
    """Verify DELETE /documents/{id} succeeds for owner and removes document."""
    txt_bytes = b"Temporary note to delete\n"
    files = {"file": ("temp.txt", txt_bytes, "text/plain")}
    headers = {"X-User-Id": "user_deleter"}

    upload_resp = api_client.post("/documents", files=files, headers=headers)
    doc_id = upload_resp.json()["doc_id"]

    del_resp = api_client.delete(f"/documents/{doc_id}", headers=headers)
    assert del_resp.status_code == 200

    # Ensure it no longer exists
    get_resp = api_client.get(f"/documents/{doc_id}", headers=headers)
    assert get_resp.status_code == 404
