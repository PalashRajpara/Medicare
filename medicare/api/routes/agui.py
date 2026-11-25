"""Standardized Protocol Bridge (AG-UI) router."""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from medicare.agents.registry import registry
from medicare.domain.models import AGUIRunRequest, StreamRequest
from medicare.security.auth import verify_bearer_auth

router = APIRouter(prefix="/agui", tags=["AG-UI Protocol Bridge"])


async def _agui_event_adapter(
    agent_id: str | None,
    payload: AGUIRunRequest,
    checkpointer,
    memory_store,
) -> AsyncGenerator[str, None]:
    """Translate native graph lifecycle events into AG-UI compliant SSE protocol."""
    last_user_message = ""
    for m in reversed(payload.messages):
        if m.get("role") in ("user", "human"):
            last_user_message = m.get("content", "")
            break

    stream_req = StreamRequest(
        message=last_user_message,
        thread_id=payload.thread_id,
        user_id=payload.user_id,
        model=payload.properties.get("model"),
        agent_config=payload.properties.get("agent_config", {}),
        stream_tokens=True,
    )

    agent = registry.get_agent(agent_id)
    from medicare.runtime.context import ExecutionContext

    context = ExecutionContext(
        run_id=payload.run_id,
        thread_id=payload.thread_id,
        user_id=payload.user_id,
        agent_id=agent.key,
        model=payload.properties.get("model", "default"),
    )

    # Initial Run Started event
    yield f"data: {json.dumps({'event': 'run_started', 'run_id': context.run_id})}\n\n"

    async for chunk in agent.stream(
        context=context,
        message=last_user_message,
        checkpointer=checkpointer,
        memory_store=memory_store,
        stream_tokens=True,
        agent_config=stream_req.agent_config,
    ):
        # Filter raw internal prompts or translate
        if "data: [DONE]" in chunk:
            yield f"data: {json.dumps({'event': 'run_completed', 'run_id': context.run_id})}\n\n"
            yield chunk
        else:
            yield chunk


@router.post(
    "/{agent_id}/run",
    dependencies=[Depends(verify_bearer_auth)],
)
async def agui_run_agent(
    agent_id: str, payload: AGUIRunRequest, request: Request
) -> EventSourceResponse:
    """Execute run over standardized AG-UI protocol for an explicit agent."""
    from medicare.api.app import get_app_checkpointer, get_app_memory_store

    gen = _agui_event_adapter(agent_id, payload, get_app_checkpointer(), get_app_memory_store())
    return EventSourceResponse(gen, media_type="text/event-stream")


@router.post(
    "/run",
    dependencies=[Depends(verify_bearer_auth)],
)
async def agui_run_default(payload: AGUIRunRequest, request: Request) -> EventSourceResponse:
    """Execute run over standardized AG-UI protocol for default agent."""
    from medicare.api.app import get_app_checkpointer, get_app_memory_store

    gen = _agui_event_adapter(None, payload, get_app_checkpointer(), get_app_memory_store())
    return EventSourceResponse(gen, media_type="text/event-stream")
