"""MediCare & Claim Navigator Supervisor Agent powered by compiled LangGraph."""

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from medicare.agents.base import BaseAgent
from medicare.config import settings
from medicare.config_loader import msg
from medicare.domain.models import ChatMessage
from medicare.domain.protocols import (
    CheckpointStoreProtocol,
    MemoryStoreProtocol,
    ModelProviderProtocol,
)
from medicare.medicare.graph.build import build_navigator_graph
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.state import (
    NavigatorState,
    PolicyAgentResult,
    SQLAgentResult,
    SupervisorPlan,
)
from medicare.providers.router import router
from medicare.rag.retriever import HybridRetriever
from medicare.runtime.context import ExecutionContext
from medicare.runtime.engine import ExecutionEngine
from medicare.runtime.events import (
    encode_agent_status_event,
    encode_done_marker,
    encode_message_event,
    encode_token_event,
)
from medicare.tools.policy_search import PolicySearchTool
from medicare.tools.sql_query import SQLiteQueryTool

logger = logging.getLogger(__name__)


class MediCareNavigatorAgent(BaseAgent):
    """Supervisor agent coordinating LangGraph multi-agent execution."""

    key = "medicare-navigator"
    description = "Healthcare cost and policy navigator."

    def __init__(
        self,
        provider: ModelProviderProtocol | None = None,
        sql_tool: SQLiteQueryTool | None = None,
        policy_tool: PolicySearchTool | None = None,
        retriever: HybridRetriever | None = None,
    ) -> None:
        self.provider = provider or router
        self.sql_tool = sql_tool or SQLiteQueryTool()
        self.policy_tool = policy_tool or PolicySearchTool()
        self.retriever = retriever or HybridRetriever()
        self._compiled_graph: Any = None

    def _get_graph(
        self,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
    ) -> Any:
        if self._compiled_graph is None:
            deps = Dependencies(
                settings=settings,
                provider=self.provider,
                sql_tool=self.sql_tool,
                policy_tool=self.policy_tool,
                retriever=self.retriever,
                memory_store=memory_store,
                checkpointer=checkpointer,
            )
            self._compiled_graph = build_navigator_graph(deps)
        return self._compiled_graph

    def _build_medicare_metadata(
        self,
        state: dict[str, Any],
        doc_scope: str = "both",
    ) -> dict[str, Any]:
        """Construct the exact required response_metadata.medicare superset payload."""
        plan: SupervisorPlan = state.get("plan") or SupervisorPlan()
        sql_res: SQLAgentResult | None = state.get("sql_result")
        policy_res: PolicyAgentResult | None = state.get("policy_result")
        guardrail = state.get("guardrail")
        grounding = state.get("grounding")
        chart = state.get("chart")

        citations_list = (
            [c.model_dump(mode="json") for c in policy_res.citations]
            if policy_res and policy_res.citations
            else []
        )
        sql_trace_list = (
            [a.model_dump(mode="json") for a in sql_res.attempts]
            if sql_res and sql_res.attempts
            else []
        )
        table_dict = sql_res.table.model_dump(mode="json") if sql_res and sql_res.table else None
        chart_dict = chart.model_dump(mode="json") if chart else None

        trace_entries = [
            t.model_dump(mode="json") if hasattr(t, "model_dump") else t
            for t in state.get("trace", [])
        ]
        timings_dict = state.get("timings", {})

        return {
            "medicare": {
                # Legacy contract keys (strictly preserved)
                "route": plan.route,
                "citations": citations_list,
                "sql_trace": sql_trace_list,
                "table": table_dict,
                "chart": chart_dict,
                "disclaimers": [
                    msg("fallback_disclaimer"),
                ],
                "guardrail": {
                    "blocked": guardrail.blocked if guardrail else False,
                    "category": guardrail.category if guardrail else None,
                },
                "followups": state.get("followups", []),
                # Extended LangGraph & Grounding keys
                "plan": plan.model_dump(mode="json"),
                "graph_trace": trace_entries,
                "timings_ms": timings_dict,
                "grounding": (
                    grounding.model_dump(mode="json")
                    if grounding
                    else {
                        "passed": True,
                        "issues": [],
                        "regenerated": False,
                        "fallback_used": False,
                    }
                ),
                "retrieval": {
                    "mode": "hybrid",
                    "rewrites_used": policy_res.rewrites_used if policy_res else 0,
                    "insurer_fallback": policy_res.insurer_fallback if policy_res else False,
                    "no_evidence": policy_res.no_evidence if policy_res else False,
                    "scope": doc_scope,
                },
            }
        }

    async def invoke(
        self,
        context: ExecutionContext,
        message: str,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """Execute single turn by consuming the graph stream (eliminates duplicated code path)."""
        final_message: ChatMessage | None = None

        async for sse_line in self.stream(
            context=context,
            message=message,
            checkpointer=checkpointer,
            memory_store=memory_store,
            stream_tokens=False,
            agent_config=agent_config,
        ):
            if sse_line.startswith("data: ") and '"type": "message"' in sse_line:
                raw_json = sse_line[6:].strip()
                try:
                    payload = json.loads(raw_json)
                    final_message = ChatMessage.model_validate(payload["content"])
                except Exception as e:
                    logger.error(f"Stream message parse error: {e}")

        if final_message is None:
            final_message = ChatMessage(
                type="ai",
                content=msg("operational_error"),
                run_id=context.run_id,
            )
        return final_message

    async def stream(
        self,
        context: ExecutionContext,
        message: str,
        checkpointer: CheckpointStoreProtocol,
        memory_store: MemoryStoreProtocol,
        stream_tokens: bool = True,
        agent_config: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Execute LangGraph multi-agent execution streaming custom statuses and tokens."""
        engine = ExecutionEngine(checkpointer)
        history = await engine.load_history(context.thread_id)

        graph = self._get_graph(checkpointer, memory_store)
        doc_scope = (agent_config or {}).get("doc_scope", "both")

        input_state: NavigatorState = {
            "question": message,
            "history": [m.model_dump(mode="json") for m in history[-6:]],
            "user_id": context.user_id or "default_user",
            "thread_id": context.thread_id,
            "run_id": context.run_id,
            "doc_scope": doc_scope,
            "trace": [],
            "timings": {},
            "llm_calls": 0,
            "regenerations": 0,
        }

        user_hash = hashlib.sha256((context.user_id or "anon").encode("utf-8")).hexdigest()[:12]
        config = {
            "recursion_limit": settings.GRAPH_RECURSION_LIMIT,
            "configurable": {"thread_id": f"{context.thread_id}:{context.run_id}"},
            "run_name": "MediCareNavigatorRun",
            "tags": ["medicare"],
            "metadata": {
                "user_id_hash": user_hash,
                "thread_id": context.thread_id,
                "run_id": context.run_id,
            },
        }

        accumulated_state: dict[str, Any] = dict(input_state)

        try:
            async with asyncio.timeout(settings.GRAPH_TIMEOUT_SECONDS):
                async for mode, chunk in graph.astream(
                    input_state,
                    config=config,
                    stream_mode=["custom", "updates"],
                ):
                    if mode == "custom":
                        if chunk.get("kind") == "status":
                            mapped_chunk = dict(chunk)
                            node_map = {
                                "supervisor": "router",
                                "sql_agent": "sql",
                                "policy_agent": "policy_rag",
                            }
                            if mapped_chunk.get("node") in node_map:
                                mapped_chunk["node"] = node_map[mapped_chunk["node"]]
                            yield encode_agent_status_event(mapped_chunk)
                        elif chunk.get("kind") == "token" and stream_tokens:
                            yield encode_token_event(chunk.get("text", ""))
                    elif mode == "updates" and isinstance(chunk, dict):
                        for node_name, node_update in chunk.items():
                            if isinstance(node_update, dict):
                                for k, v in node_update.items():
                                    if k in ("trace", "timings", "llm_calls"):
                                        # Reducers handled
                                        if k == "trace":
                                            accumulated_state["trace"] = (
                                                accumulated_state.get("trace", []) + v
                                            )
                                        elif k == "timings":
                                            accumulated_state["timings"] = {
                                                **accumulated_state.get("timings", {}),
                                                **v,
                                            }
                                    else:
                                        accumulated_state[k] = v
        except TimeoutError:
            logger.error("Graph execution timed out.")
            yield encode_agent_status_event(
                {
                    "node": "verifier",
                    "status": "fallback",
                    "message": msg("execution_timeout"),
                }
            )
            accumulated_state["answer"] = msg("execution_timeout")
        except Exception as e:
            logger.error(f"Execution error: {e}")
            accumulated_state["answer"] = f"{msg('operational_error')}: {e}"

        # Construct final ChatMessage
        answer_text = accumulated_state.get("answer") or "No response generated."
        medicare_meta = self._build_medicare_metadata(accumulated_state, doc_scope=doc_scope)

        ai_msg = ChatMessage(
            type="ai",
            content=answer_text,
            run_id=context.run_id,
            response_metadata=medicare_meta,
        )

        yield encode_message_event(ai_msg)
        yield encode_done_marker()

        # Persist turn in short-term checkpointer
        user_msg = ChatMessage(
            type="human",
            content=accumulated_state.get("question", message),
        )
        await engine.persist_turn(context, history + [user_msg, ai_msg], len(history) + 2)
