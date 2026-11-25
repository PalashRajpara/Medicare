"""Standardized Protocol Bridge (AG-UI) tests."""

from fastapi.testclient import TestClient


def test_agui_run_endpoint(client: TestClient):
    payload = {
        "messages": [{"role": "user", "content": "What is 10 + 20?"}],
        "run_id": "agui-run-12345",
        "thread_id": "agui-thread-67890",
        "properties": {
            "model": "mock-gpt-4",
            "agent_config": {"domain": "math"},
        },
    }

    with client.stream("POST", "/agui/medicare-navigator/run", json=payload) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = list(resp.iter_lines())

        # Check for AG-UI run_started and completed events
        has_started = any("run_started" in line for line in lines)
        has_done = any("[DONE]" in line for line in lines)

        assert has_started is True
        assert has_done is True
