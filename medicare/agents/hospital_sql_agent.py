"""Hospital SQL Agent executing self-correcting query loops over hospital records."""

from collections.abc import AsyncGenerator, Callable
from typing import Any

from pydantic import BaseModel

from medicare.agents.base import BaseAgent
from medicare.config_loader import msg
from medicare.domain.models import ChatMessage, SQLAttempt, TableResult
from medicare.domain.protocols import (
    CheckpointStoreProtocol,
    MemoryStoreProtocol,
    ModelProviderProtocol,
)
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.sql_subgraph import build_sql_graph
from medicare.providers.router import router
from medicare.runtime.context import ExecutionContext
from medicare.runtime.engine import ExecutionEngine
from medicare.runtime.events import (
    encode_done_marker,
    encode_message_event,
    encode_token_event,
)
from medicare.tools.sql_query import SQLiteQueryTool


class SQLLoopResult(BaseModel):
    """Result of self-correcting SQL loop execution."""

    success: bool
    table: TableResult | None = None
    final_sql: str | None = None
    attempts: list[SQLAttempt] = []
    database_empty: bool = False


async def run_sql_loop(
    question: str,
    ctx: ExecutionContext,
    emit: Callable[[str, Any], Any] | None = None,
    provider: ModelProviderProtocol | None = None,
    sql_tool: SQLiteQueryTool | None = None,
) -> SQLLoopResult:
    """Execute the self-correcting SQL sub-graph (1 initial + up to 3 fix attempts = 4 max)."""
    p = provider or router
    t = sql_tool or SQLiteQueryTool()

    deps = Dependencies.default()
    deps.provider = p
    deps.sql_tool = t

    graph = build_sql_graph(deps)
    sub_input = {
        "question": question,
        "attempts": [],
        "retry_count": 0,
    }

    final_sub_state: dict[str, Any] = {}
    async for mode, chunk in graph.astream(sub_input, stream_mode=["custom", "values"]):
        if mode == "custom" and emit:
            if isinstance(chunk, dict) and chunk.get("kind") == "status":
                await emit(chunk.get("node", "sql_agent"), chunk)
        elif mode == "values":
            final_sub_state = chunk

    return SQLLoopResult(
        success=final_sub_state.get("success", False),
        table=final_sub_state.get("table"),
        final_sql=final_sub_state.get("final_sql"),
        attempts=final_sub_state.get("attempts", []),
        database_empty=final_sub_state.get("empty_db", False),
    )


class HospitalSQLAgent(BaseAgent):
    """Standalone agent dedicated to self-correcting queries over hospital records."""

    key = "hospital-sql"
    description = "Hospital records query."

    def __init__(
        self,
        provider: ModelProviderProtocol | None = None,
        sql_tool: SQLiteQueryTool | None = None,
    ) -> None:
        self.provider = provider or router
        self.sql_tool = sql_tool or SQLiteQueryTool()

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

        loop_res = await run_sql_loop(
            question=message,
            ctx=context,
            provider=self.provider,
            sql_tool=self.sql_tool,
        )

        if loop_res.success and loop_res.table and loop_res.table.rows:
            tbl = loop_res.table
            col_line = " | ".join(tbl.columns)
            sep_line = " | ".join(["---"] * len(tbl.columns))
            rows_str = [f"| {col_line} |", f"| {sep_line} |"]
            for r in tbl.rows:
                rows_str.append("| " + " | ".join(str(c) for c in r) + " |")
            content = "### Hospital Query Results\n\n" + "\n".join(rows_str)
        elif loop_res.database_empty:
            content = msg("zero_records_found")
        else:
            err = loop_res.attempts[-1].error if loop_res.attempts else "Unable to execute query."
            content = f"Could not retrieve records: {err}"

        meta = {
            "sql_trace": [a.model_dump() for a in loop_res.attempts],
            "table": loop_res.table.model_dump() if loop_res.table else None,
            "final_sql": loop_res.final_sql,
        }

        user_msg = ChatMessage(type="human", content=message)
        ai_msg = ChatMessage(
            type="ai",
            content=content,
            run_id=context.run_id,
            response_metadata={"medicare_sql": meta},
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
