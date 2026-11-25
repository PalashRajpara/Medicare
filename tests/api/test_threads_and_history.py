"""History and thread discovery endpoints with tenant isolation tests."""

from fastapi.testclient import TestClient


def test_history_and_threads_flow(client: TestClient):
    thread_id = "tenant-isolation-th-1"
    user_id = "tenant-user-alpha"

    # 1. Invoke to establish history
    inv_payload = {
        "message": "First message from User Alpha",
        "thread_id": thread_id,
        "user_id": user_id,
    }
    client.post("/medicare-navigator/invoke", json=inv_payload)

    # 2. History retrieval
    hist_resp = client.post("/history", json={"thread_id": thread_id})
    assert hist_resp.status_code == 200
    messages = hist_resp.json()["messages"]
    assert len(messages) >= 2
    assert messages[0]["content"] == "First message from User Alpha"

    # 3. Threads enumeration for user_id
    threads_resp = client.get("/threads", params={"user_id": user_id})
    assert threads_resp.status_code == 200
    th_list = threads_resp.json()["threads"]
    assert len(th_list) >= 1
    assert th_list[0]["thread_id"] == thread_id

    # 4. Strict tenant isolation: other user sees empty list
    other_threads = client.get("/threads", params={"user_id": "different-user-beta"})
    assert other_threads.status_code == 200
    assert len(other_threads.json()["threads"]) == 0
