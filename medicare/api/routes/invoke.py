"""Synchronous agent invocation router."""

from fastapi import APIRouter, Depends

from medicare.agents.registry import registry
from medicare.domain.models import ChatMessage, InvokeRequest
from medicare.runtime.context import ExecutionContext
from medicare.security.auth import verify_bearer_auth
from medicare.security.sanitization import validate_agent_config, validate_requested_model

router = APIRouter(tags=["Invocation"])


async def _execute_invocation(
    agent_id: str | None,
    payload: InvokeRequest,
    checkpointer,
    memory_store,
) -> ChatMessage:
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

    return await agent.invoke(
        context=context,
        message=payload.message,
        checkpointer=checkpointer,
        memory_store=memory_store,
        agent_config=validated_config,
    )


@router.post(
    "/{agent_id}/invoke",
    response_model=ChatMessage,
    dependencies=[Depends(verify_bearer_auth)],
)
async def invoke_agent(agent_id: str, payload: InvokeRequest) -> ChatMessage:
    """Execute a turn against an explicitly named agent."""
    from medicare.api.app import get_app_checkpointer, get_app_memory_store

    return await _execute_invocation(
        agent_id, payload, get_app_checkpointer(), get_app_memory_store()
    )


@router.post(
    "/invoke",
    response_model=ChatMessage,
    dependencies=[Depends(verify_bearer_auth)],
)
async def invoke_default_agent(payload: InvokeRequest) -> ChatMessage:
    """Execute a turn against the system default agent."""
    from medicare.api.app import get_app_checkpointer, get_app_memory_store

    return await _execute_invocation(None, payload, get_app_checkpointer(), get_app_memory_store())
