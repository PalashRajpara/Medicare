"""HTTP and SSE client connecting the Streamlit frontend to MediCare Gateway."""

import json
import os
from collections.abc import Callable, Generator
from typing import Any

import httpx

from ui.config import get_app_config


class MediCareClient:
    """Client for synchronous, streaming, and metadata API calls."""

    def __init__(
        self,
        base_url: str | None = None,
        secret_token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        default_url = get_app_config().get("ui", {}).get("backend_service_url", "")
        self.base_url = (base_url or os.getenv("BACKEND_SERVICE_URL") or default_url).rstrip("/")
        self.secret_token = secret_token
        self.transport = transport

    def _client(self, timeout: float = 5.0) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, transport=self.transport, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.secret_token:
            headers["Authorization"] = f"Bearer {self.secret_token}"
        return headers

    def check_health(self) -> bool:
        """Check if backend service is alive and healthy."""
        try:
            with self._client(timeout=3.0) as client:
                resp = client.get("/health", headers=self._headers())
                return resp.status_code == 200
        except Exception:
            return False

    def get_app_config(self) -> dict[str, Any]:
        """Fetch application configuration and UI labels from backend."""
        with self._client(timeout=5.0) as client:
            resp = client.get("/app/config", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_info(self) -> dict[str, Any]:
        """Fetch registered agents and foundational models."""
        with self._client(timeout=5.0) as client:
            resp = client.get("/info", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_medicare_status(self) -> dict[str, Any]:
        """Fetch live database counts and vector index status from Medicare status API."""
        with self._client(timeout=5.0) as client:
            resp = client.get("/medicare/status", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_medicare_suggestions(self, user_id: str | None = None) -> list[str]:
        """Fetch suggested questions from backend based on live database values."""
        params = {}
        if user_id:
            params["user_id"] = user_id
        with self._client(timeout=5.0) as client:
            resp = client.get("/medicare/suggestions", params=params, headers=self._headers())
            if resp.status_code == 200:
                data = resp.json()
                return data.get("suggestions", [])
            return []

    def stream(
        self,
        agent_id: str,
        message: str,
        thread_id: str,
        user_id: str,
        model: str | None = None,
        stream_tokens: bool = True,
        doc_scope: str = "both",
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Stream events from the multi-agent execution pipeline via SSE."""
        endpoint = f"/{agent_id}/stream" if agent_id else "/stream"
        url = f"{self.base_url}{endpoint}"
        payload = {
            "message": message,
            "thread_id": thread_id,
            "user_id": user_id,
            "model": model,
            "stream_tokens": stream_tokens,
            "doc_scope": doc_scope,
            "metadata": {"doc_scope": doc_scope},
        }

        with (
            self._client(timeout=180.0) as http_client,
            http_client.stream(
                "POST",
                url,
                json=payload,
                headers=self._headers(),
            ) as response,
        ):
            response.raise_for_status()
            for line in response.iter_lines():
                if is_cancelled and is_cancelled():
                    break
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data_str)
                        yield parsed
                    except json.JSONDecodeError:
                        yield {"type": "raw", "content": data_str}

    def list_threads(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """List prior conversation threads for the user."""
        with self._client(timeout=5.0) as client:
            resp = client.get(f"/threads?user_id={user_id}&limit={limit}", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("threads", [])
            return data if isinstance(data, list) else []

    def get_history(self, thread_id: str) -> list[dict[str, Any]]:
        """Retrieve historical messages for a thread."""
        with self._client(timeout=5.0) as client:
            resp = client.post("/history", json={"thread_id": thread_id}, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("messages", [])
            return data if isinstance(data, list) else []

    def submit_feedback(
        self,
        run_id: str,
        score: float,
        feedback_text: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Submit user evaluation score for an execution run."""
        url = "/feedback"
        payload = {
            "run_id": run_id,
            "key": "human-feedback-stars",
            "score": score,
            "kwargs": {"feedback_text": feedback_text, "user_id": user_id},
        }
        with self._client(timeout=5.0) as client:
            resp = client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        insurer: str | None = None,
        doc_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload a user document (policy or bill) to the backend."""
        files = {"file": (filename, file_bytes)}
        data: dict[str, Any] = {"user_id": user_id}
        if insurer:
            data["insurer"] = insurer
        if doc_type:
            data["doc_type"] = doc_type

        headers = {}
        if self.secret_token:
            headers["Authorization"] = f"Bearer {self.secret_token}"

        with self._client(timeout=60.0) as client:
            resp = client.post("/documents", files=files, data=data, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def list_documents(
        self, user_id: str | None = None, scope: str = "all"
    ) -> list[dict[str, Any]]:
        """List documents available to user (mine, curated, or all)."""
        params = {"scope": scope}
        if user_id:
            params["user_id"] = user_id
        with self._client(timeout=5.0) as client:
            resp = client.get("/documents", params=params, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("documents", [])
            return data if isinstance(data, list) else []

    def get_document(self, doc_id: str, user_id: str | None = None) -> dict[str, Any]:
        """Poll document indexing status."""
        params = {}
        if user_id:
            params["user_id"] = user_id
        with self._client(timeout=5.0) as client:
            resp = client.get(f"/documents/{doc_id}", params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def delete_document(self, doc_id: str, user_id: str) -> dict[str, Any]:
        """Delete user-uploaded document."""
        params = {"user_id": user_id}
        with self._client(timeout=5.0) as client:
            resp = client.delete(f"/documents/{doc_id}", params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
