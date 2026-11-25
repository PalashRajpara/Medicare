"""Run evaluation feedback router."""

from fastapi import APIRouter, Depends

from medicare.domain.models import FeedbackRequest, FeedbackResponse
from medicare.security.auth import verify_bearer_auth
from medicare.telemetry.tracer import telemetry

router = APIRouter(tags=["Telemetry Feedback"])


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """Record human evaluation rating (0.0 to 1.0) tied to an execution run ID."""
    await telemetry.record_feedback(
        run_id=payload.run_id,
        key=payload.key,
        score=payload.score,
        kwargs=payload.kwargs,
    )
    return FeedbackResponse(status="success")
