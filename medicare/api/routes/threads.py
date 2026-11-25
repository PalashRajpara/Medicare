"""Thread history reconstruction and user thread discovery router."""

from fastapi import APIRouter, Depends, Query

from medicare.domain.models import (
    HistoryRequest,
    HistoryResponse,
    ThreadListResponse,
)
from medicare.security.auth import verify_bearer_auth

router = APIRouter(tags=["Threads & History"])


@router.post(
    "/{agent_id}/history",
    response_model=HistoryResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def get_agent_history(agent_id: str, payload: HistoryRequest) -> HistoryResponse:
    """Retrieve full message history for a given thread."""
    from medicare.api.app import get_app_checkpointer

    msgs = await get_app_checkpointer().get_thread_history(payload.thread_id)
    return HistoryResponse(messages=msgs)


@router.post(
    "/history",
    response_model=HistoryResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def get_history(payload: HistoryRequest) -> HistoryResponse:
    """Retrieve full message history for a given thread."""
    from medicare.api.app import get_app_checkpointer

    msgs = await get_app_checkpointer().get_thread_history(payload.thread_id)
    return HistoryResponse(messages=msgs)


@router.get(
    "/{agent_id}/threads",
    response_model=ThreadListResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def list_agent_threads(
    agent_id: str,
    user_id: str = Query(..., description="Target user identifier"),
    limit: int = Query(20, ge=1, le=100),
) -> ThreadListResponse:
    """List recent conversation sessions for a user within a specific agent."""
    from medicare.api.app import get_app_checkpointer

    threads = await get_app_checkpointer().list_threads(
        user_id=user_id, agent_id=agent_id, limit=limit
    )
    return ThreadListResponse(threads=threads)


@router.get(
    "/threads",
    response_model=ThreadListResponse,
    dependencies=[Depends(verify_bearer_auth)],
)
async def list_all_user_threads(
    user_id: str = Query(..., description="Target user identifier"),
    limit: int = Query(20, ge=1, le=100),
) -> ThreadListResponse:
    """List recent conversation sessions for a user across all agents."""
    from medicare.api.app import get_app_checkpointer

    threads = await get_app_checkpointer().list_threads(user_id=user_id, agent_id=None, limit=limit)
    return ThreadListResponse(threads=threads)
