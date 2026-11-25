"""Integration tests for FastAPI gateway endpoints."""

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "telemetry" in data


def test_info_endpoint(client: TestClient):
    resp = client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert len(data["agents"]) == 3
    assert "models" in data
    assert data["default_agent"] == "medicare-navigator"


def test_invoke_explicit_agent(client: TestClient):
    payload = {
        "message": "Hello",
        "thread_id": "test-thread-invoke-1",
        "model": "mock-gpt-4",
    }
    resp = client.post("/medicare-navigator/invoke", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "ai"
    assert data["content"] != ""


def test_invoke_default_agent(client: TestClient):
    payload = {
        "message": "Hello from default agent test",
    }
    resp = client.post("/invoke", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "ai"


def test_invoke_disallowed_model(client: TestClient):
    payload = {
        "message": "Test model reject",
        "model": "non-existent-super-model-404",
    }
    resp = client.post("/invoke", json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "ModelNotAllowedError" in data["error"]


def test_invoke_reserved_parameter_rejection(client: TestClient):
    payload = {
        "message": "Inject reserved key",
        "agent_config": {"thread_id": "malicious_override"},
    }
    resp = client.post("/invoke", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert "ReservedParameterError" in data["error"]


def test_feedback_endpoint(client: TestClient):
    payload = {
        "run_id": "run-test-uuid-999",
        "score": 0.8,
        "kwargs": {"comment": "Great response!"},
    }
    resp = client.post("/feedback", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_medicare_suggestions_endpoint(client: TestClient):
    resp = client.get("/medicare/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data
    assert len(data["suggestions"]) >= 3
    for s in data["suggestions"]:
        assert isinstance(s, str)
        assert len(s) > 10
