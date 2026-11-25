"""Policy RAG Agent retrieving and citing health insurance clauses."""

from collections.abc import AsyncGenerator
from typing import Any

from medicare.agents.base import BaseAgent
from medicare.config_loader import msg
from medicare.domain.models import ChatMessage, Citation
from medicare.domain.protocols import (
    CheckpointStoreProtocol,
    MemoryStoreProtocol,
)
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.policy_subgraph import build_policy_graph
from medicare.runtime.context import ExecutionContext
from medicare.runtime.engine import ExecutionEngine
from medicare.runtime.events import (
    encode_done_marker,
    encode_message_event,
    encode_token_event,
)
from medicare.tools.policy_search import PolicySearchTool


def retrieve_policy(
    question: str,
    insurer: str | None = None,
    top_k: int = 5,
    policy_tool: PolicySearchTool | None = None,
) -> list[Citation]:
    """Retrieve insurance policy citations strictly grounded in indexed markdown documents."""
    tool = policy_tool or PolicySearchTool()
    return tool.search(query=question, insurer=insurer, top_k=top_k)


class PolicyRAGAgent(BaseAgent):
    """Standalone agent dedicated to insurance policy clause retrieval and citation grounding."""

    key = "policy-rag"
    description = "Policy document retrieval and grounding."

    def __init__(self, policy_tool: PolicySearchTool | None = None) -> None:
        self.policy_tool = policy_tool or PolicySearchTool()

    async def invoke(
        self,
        context: ExecutionContext,
        message: str,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        engine = ExecutionEngine(checkpointer)
        history = await engine.load_history(context.thread_id)

        deps = Dependencies.default()
        deps.policy_tool = self.policy_tool
        policy_graph = build_policy_graph(deps)

        doc_scope = (agent_config or {}).get("doc_scope", "both")
        sub_input = {
            "question": message,
            "user_id": context.user_id,
            "doc_scope": doc_scope,
        }

        final_sub_state: dict[str, Any] = {}
        async for mode, chunk in policy_graph.astream(sub_input, stream_mode=["values"]):
            if mode == "values":
                final_sub_state = chunk

        citations = final_sub_state.get("citations") or retrieve_policy(
            message, policy_tool=self.policy_tool
        )

        if not citations:
            content = msg("policy_search_no_match")
        else:
            chunks_formatted = []
            for idx, c in enumerate(citations, start=1):
                cite_id = c.cite_id or f"C{idx}"
                page_str = f", Page {c.page}" if c.page else ""
                chunks_formatted.append(
                    f"### [{cite_id}] {c.section} (Source: {c.source}{page_str}, Score: {c.score})\n{c.text}"
                )
            content = f"Found {len(citations)} relevant policy clauses:\n\n" + "\n\n".join(
                chunks_formatted
            )

        meta = {
            "citations": [c.model_dump() for c in citations],
            "retrieval_count": len(citations),
        }

        user_msg = ChatMessage(type="human", content=message)
        ai_msg = ChatMessage(
            type="ai",
            content=content,
            run_id=context.run_id,
            response_metadata={"medicare_policy": meta},
        )

        await engine.persist_turn(context, history + [user_msg, ai_msg], len(history) + 2)
        return ai_msg

    async def stream(
        self,
        context: ExecutionContext,
        message: str,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
        stream_tokens: bool = True,
        agent_config: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        msg = await self.invoke(
            context=context,
            message=message,
            checkpointer=checkpointer,
            memory_store=memory_store,
            agent_config=agent_config,
        )

        if stream_tokens:
            for word in msg.content.split(" "):
                yield encode_token_event(word + " ")

        yield encode_message_event(msg)
        yield encode_done_marker()
