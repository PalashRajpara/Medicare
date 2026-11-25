"""Mock HTTP and SSE streaming tests for MediCareClient."""

import json

import httpx

from ui.client import MediCareClient


def test_client_check_health():
    """Verify health check probe returns True on 200 and False on failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "telemetry": "connected"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = MediCareClient(base_url="http://testserver", transport=transport)
    assert client.check_health() is True
    assert client.base_url == "http://testserver"


def test_client_get_app_config():
    """Verify get_app_config retrieves application labels."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/config":
            return httpx.Response(200, json={"app_name": "MediCare", "features": {"voice": False}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = MediCareClient(base_url="http://testserver", transport=transport)
    data = client.get_app_config()
    assert data["app_name"] == "MediCare"
    assert data["features"]["voice"] is False


def test_client_stream_sse_parsing():
    """Verify SSE streaming yields parsed status, token, and message events."""
    sse_body = (
        'data: {"type": "agent_status", "content": {"node": "supervisor", "status": "running"}}\n\n'
        'data: {"type": "token", "content": "Hello"}\n\n'
        'data: {"type": "token", "content": " World"}\n\n'
        'data: {"type": "message", "content": {"type": "ai", "content": "Hello World"}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/medicare-navigator/stream"
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    client = MediCareClient(base_url="http://testserver", transport=transport)
    received_events = list(
        client.stream(
            agent_id="medicare-navigator",
            message="Hello",
            thread_id="t-1",
            user_id="u-1",
        )
    )

    assert len(received_events) == 4
    assert received_events[0]["type"] == "agent_status"
    assert received_events[1]["type"] == "token"
    assert received_events[1]["content"] == "Hello"
    assert received_events[2]["content"] == " World"
    assert received_events[3]["type"] == "message"


def test_client_stream_cancellation():
    """Verify SSE stream cleanly breaks when cancel callback triggers."""
    sse_body = (
        'data: {"type": "token", "content": "Part 1"}\n\n'
        'data: {"type": "token", "content": "Part 2"}\n\n'
        'data: {"type": "token", "content": "Part 3"}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    cancelled = False

    def is_cancelled() -> bool:
        return cancelled

    client = MediCareClient(base_url="http://testserver", transport=transport)
    received_tokens = []
    for event in client.stream(
        agent_id="medicare-navigator",
        message="test",
        thread_id="t-1",
        user_id="u-1",
        is_cancelled=is_cancelled,
    ):
        if event.get("type") == "token":
            received_tokens.append(event.get("content"))
            # Cancel after first token
            cancelled = True

    assert received_tokens == ["Part 1"]


def test_client_documents_and_feedback():
    """Verify feedback submission, document upload, and deletion endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feedback" and request.method == "POST":
            payload = json.loads(request.content)
            assert payload["run_id"] == "run-123"
            assert payload["score"] == 1.0
            return httpx.Response(200, json={"status": "success"})
        if request.url.path == "/documents" and request.method == "GET":
            return httpx.Response(200, json={"documents": [{"doc_id": "d-1", "title": "Doc 1"}]})
        if request.url.path == "/documents/d-1" and request.method == "DELETE":
            return httpx.Response(200, json={"status": "deleted", "doc_id": "d-1"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = MediCareClient(base_url="http://testserver", transport=transport)

    fb_resp = client.submit_feedback(run_id="run-123", score=1.0)
    assert fb_resp["status"] == "success"

    doc_resp = client.list_documents()
    assert len(doc_resp) == 1

    del_resp = client.delete_document(doc_id="d-1", user_id="u-1")
    assert del_resp["status"] == "deleted"
