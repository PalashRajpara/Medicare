"""Real-time Server-Sent Events (SSE) streaming invocation router."""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from medicare.agents.registry import registry
from medicare.domain.models import StreamRequest
from medicare.runtime.context import ExecutionContext
from medicare.security.auth import verify_bearer_auth
from medicare.security.sanitization import validate_agent_config, validate_requested_model

router = APIRouter(tags=["Streaming"])


async def _stream_generator(
    agent_id: str | None,
    payload: StreamRequest,
    checkpointer,
    memory_store,
) -> AsyncGenerator[str, None]:
    try:
        agent = registry.get_agent(agent_id)
        validated_model = validate_requested_model(payload.model)
        validated_config = validate_agent_config(payload.agent_config) or {}
        if hasattr(payload, "doc_scope") and payload.doc_scope:
            validated_config["doc_scope"] = payload.doc_scope

        context = ExecutionContext(
            thread_id=payload.thread_id,
            user_id=payload.user_id,
            agent_id=agent.key,
            model=validated_model,
        )

        async for chunk in agent.stream(
            context=context,
            message=payload.message,
            checkpointer=checkpointer,
            memory_store=memory_store,
            stream_tokens=payload.stream_tokens,
            agent_config=validated_config,
        ):
            c = chunk.strip()
            while c.startswith("data:"):
                c = c[5:].strip()
            if c:
                yield c

    except Exception as err:
        yield json.dumps({"type": "error", "content": str(err)})


@router.post(
    "/{agent_id}/stream",
    dependencies=[Depends(verify_bearer_auth)],
)
async def stream_agent(
    agent_id: str, payload: StreamRequest, request: Request
) -> EventSourceResponse:
    """Stream execution events and token deltas for an explicit agent."""
    from medicare.api.app import get_app_checkpointer, get_app_memory_store

    gen = _stream_generator(agent_id, payload, get_app_checkpointer(), get_app_memory_store())
    return EventSourceResponse(gen, media_type="text/event-stream")


@router.post(
    "/stream",
    dependencies=[Depends(verify_bearer_auth)],
)
async def stream_default_agent(payload: StreamRequest, request: Request) -> EventSourceResponse:
    """Stream execution events and token deltas for the default agent."""
    from medicare.api.app import get_app_checkpointer, get_app_memory_store

    gen = _stream_generator(None, payload, get_app_checkpointer(), get_app_memory_store())
    return EventSourceResponse(gen, media_type="text/event-stream")
