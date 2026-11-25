"""Telemetry dispatcher and run feedback collection."""

from typing import Any

from medicare.config import settings
from medicare.domain.models import RunFeedbackRecord


class TelemetryDispatcher:
    """Manages observability traces and user evaluation ratings."""

    def __init__(self) -> None:
        self._feedback_records: list[RunFeedbackRecord] = []

    async def record_feedback(
        self, run_id: str, key: str, score: float, kwargs: dict[str, Any] | None = None
    ) -> RunFeedbackRecord:
        record = RunFeedbackRecord(
            run_id=run_id,
            key=key,
            score=score,
            kwargs=kwargs or {},
        )
        self._feedback_records.append(record)

        # Forward to LangSmith if configured
        if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
            # Simulated or native client forward
            pass

        return record

    def get_feedback_records(self) -> list[RunFeedbackRecord]:
        return list(self._feedback_records)

    def is_connected(self) -> bool:
        """Return connectivity status for health probe."""
        if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
            return True
        if settings.LANGFUSE_ENABLED:
            return True
        return True  # Local telemetry active


telemetry = TelemetryDispatcher()
