"""Server-Sent Events (SSE) streaming protocol integration tests."""

from fastapi.testclient import TestClient


def test_stream_explicit_agent(client: TestClient):
    payload = {
        "message": "Hello",
        "thread_id": "test-stream-thread-1",
        "stream_tokens": True,
    }
    with client.stream("POST", "/medicare-navigator/stream", json=payload) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = list(resp.iter_lines())

        # Verify event prefixes and termination marker
        has_token_or_message = any('data: {"type"' in line for line in lines)
        has_done_marker = any("data: [DONE]" in line for line in lines)

        assert has_token_or_message is True
        assert has_done_marker is True


def test_stream_default_agent(client: TestClient):
    payload = {
        "message": "Run default stream test",
        "stream_tokens": False,
    }
    with client.stream("POST", "/stream", json=payload) as resp:
        assert resp.status_code == 200
        lines = list(resp.iter_lines())
        assert any("data: [DONE]" in line for line in lines)
