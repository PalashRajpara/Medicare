"""Nodes and execution handlers for the self-correcting Hospital SQL Agent sub-graph."""

import logging
import re
from typing import Any, TypedDict

from langgraph.types import StreamWriter

from medicare.config import settings
from medicare.config_loader import msg
from medicare.domain.protocols import ModelProviderProtocol
from medicare.medicare.dataset.schema import (
    SQL_SCHEMA_PROMPT,
    format_schema_for_prompt,
    validate_sql_query,
)
from medicare.medicare.graph.events import emit_status
from medicare.medicare.graph.state import (
    SQLAttempt,
    SupervisorPlan,
    TableResult,
)
from medicare.medicare.prompts import (
    SQL_FIXER_PROMPT,
    SQL_GENERATOR_PROMPT,
    call_llm_text,
)
from medicare.tools.sql_query import SQLiteQueryTool

logger = logging.getLogger(__name__)


class SQLSubState(TypedDict, total=False):
    """Internal state for the self-correcting SQL sub-graph."""

    question: str
    plan: SupervisorPlan
    schema_prompt: str
    current_sql: str | None
    attempts: list[SQLAttempt]
    retry_count: int
    table: TableResult | None
    success: bool
    broadened: bool
    error_summary: str | None
    empty_db: bool
    final_sql: str | None
    previous_identical: bool


async def load_schema_node(
    state: SQLSubState, writer: StreamWriter | None = None
) -> dict[str, Any]:
    """Load SQLite database schema prompt and emit start status."""
    emit_status(writer, "sql_agent", "running", msg("sql_loading_schema"))
    schema = format_schema_for_prompt()
    return {
        "schema_prompt": schema,
        "attempts": state.get("attempts", []),
        "retry_count": 0,
        "broadened": False,
        "success": False,
        "previous_identical": False,
    }


async def generate_sql_node(
    state: SQLSubState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Generate initial SQLite SELECT statement from prompt and schema."""
    emit_status(writer, "sql_agent", "running", msg("sql_generating_query"))

    # Forced first failure for demo mode
    if settings.MEDICARE_DEMO_FAIL_FIRST and state.get("retry_count", 0) == 0:
        bad_sql = "SELECT hospital_name, cost FROM hospital_data LIMIT 10;"
        return {"current_sql": bad_sql}

    # If it is a ScriptedProvider, consume its scripted response directly
    if hasattr(provider, "responses"):
        raw = await call_llm_text(provider, prompt="generate sql", model="scripted-test")
        clean_sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
        return {"current_sql": clean_sql}

    plan = state.get("plan")
    q_text = (
        plan.rewritten_question if plan and plan.rewritten_question else state.get("question", "")
    )
    entities_hint = ""
    if plan and plan.entities:
        non_empty = {k: v for k, v in plan.entities.items() if v}
        if non_empty:
            entities_hint = f"CANONICAL ENTITIES TO FILTER BY: {non_empty}\n\n"

    if settings.USE_MOCK_MODELS or provider.__class__.__name__ == "MockModelEngine":
        if hasattr(provider, "_handle_medicare_sql_generator"):
            sql = provider._handle_medicare_sql_generator(q_text)
        else:
            prompt = (
                f"{SQL_GENERATOR_PROMPT}\n\n"
                f"DATABASE SCHEMA:\n{state.get('schema_prompt', SQL_SCHEMA_PROMPT)}\n\n"
                f"{entities_hint}"
                f"USER QUESTION: {q_text}\n"
            )
            raw = await call_llm_text(provider, prompt=prompt, model="mock-model")
            sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
        return {"current_sql": sql}

    # Live provider LLM completion
    prompt = (
        f"{SQL_GENERATOR_PROMPT}\n\n"
        f"DATABASE SCHEMA:\n{state.get('schema_prompt', SQL_SCHEMA_PROMPT)}\n\n"
        f"{entities_hint}"
        f"USER QUESTION: {q_text}\n"
    )
    raw = await call_llm_text(provider, prompt=prompt, model=settings.GROQ_MODEL)
    clean_sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
    return {"current_sql": clean_sql}


async def static_check_node(
    state: SQLSubState,
    sql_tool: SQLiteQueryTool,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Perform pre-execution AST/static validation without hitting the database."""
    sql = state.get("current_sql") or ""
    attempt_num = len(state.get("attempts", [])) + 1

    is_valid, reason = validate_sql_query(sql)
    if not is_valid:
        attempt = SQLAttempt(
            attempt=attempt_num,
            sql=sql,
            error=reason,
            kind="forbidden",
            row_count=0,
        )
        attempts = list(state.get("attempts", [])) + [attempt]
        emit_status(
            writer,
            "sql_agent",
            "retry",
            f"Static check failed ({reason}). Attempting fix...",
            retry=attempt_num,
            max_retries=settings.SQL_MAX_RETRIES,
        )
        return {
            "attempts": attempts,
            "retry_count": state.get("retry_count", 0) + 1,
            "error_summary": reason,
            "static_check_failed": True,
        }

    return {"static_check_failed": False}


async def execute_sql_node(
    state: SQLSubState,
    sql_tool: SQLiteQueryTool,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Execute validated SQLite query within read-only timeout transaction."""
    attempts = list(state.get("attempts", []))
    sql = state.get("current_sql") or ""
    attempt_num = len(attempts) + 1

    res = await sql_tool.execute_query_with_trace(sql, attempt_index=attempt_num)
    attempt = res.attempt
    new_attempts = attempts + [attempt]

    if res.success and res.table is not None:
        emit_status(
            writer,
            "sql_agent",
            "done",
            f"Retrieved {len(res.table.rows)} hospital records.",
        )
        return {
            "attempts": new_attempts,
            "table": res.table,
            "success": True,
            "final_sql": sql,
            "empty_db": len(res.table.rows) == 0,
        }

    # If empty database or missing database, terminate immediately without retries
    err_lower = (attempt.error or "").lower()
    if (
        attempt.kind == "empty_db"
        or "database exists but contains 0 records" in err_lower
        or "database file not found" in err_lower
    ):
        emit_status(
            writer,
            "sql_agent",
            "done",
            msg("sql_database_empty"),
        )
        return {
            "attempts": new_attempts,
            "success": False,
            "empty_db": True,
            "error_summary": attempt.error,
        }

    # Query threw SQLite error
    if attempt_num <= settings.SQL_MAX_RETRIES:
        emit_status(
            writer,
            "sql_agent",
            "retry",
            f"Execution error ({attempt.error}). Attempting fix...",
            retry=attempt_num,
            max_retries=settings.SQL_MAX_RETRIES,
        )
    return {
        "attempts": new_attempts,
        "retry_count": state.get("retry_count", 0) + 1,
        "error_summary": attempt.error,
        "success": False,
    }


async def fix_sql_node(
    state: SQLSubState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Inspect previous failed query and SQLite error to synthesize a fix."""
    attempts = state.get("attempts", [])
    last_attempt = attempts[-1] if attempts else None
    failed_sql = last_attempt.sql if last_attempt else ""
    error_msg = last_attempt.error if last_attempt else "Unknown SQL error"

    # Check for identical repeated SQL
    if len(attempts) >= 2 and attempts[-1].sql == attempts[-2].sql:
        logger.warning(msg("sql_repeated_detected"))
        return {"previous_identical": True}

    if hasattr(provider, "responses"):
        # ScriptedProvider test double
        raw = await call_llm_text(provider, prompt="fix sql", model="scripted-test")
        clean_sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
        if clean_sql == failed_sql:
            logger.warning(msg("sql_fixer_identical"))
            var_prompt = (
                f"Previous attempt was identical to '{failed_sql}'. "
                f"{msg('sql_fixer_variation_prompt')}"
            )
            raw = await call_llm_text(provider, prompt=var_prompt, model="scripted-test")
            clean_sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
        return {"current_sql": clean_sql}

    if settings.USE_MOCK_MODELS or provider.__class__.__name__ == "MockModelEngine":
        # In mock mode, repair into standard valid query
        if hasattr(provider, "_handle_medicare_sql_fixer"):
            repaired = provider._handle_medicare_sql_fixer(failed_sql)
        else:
            repaired = failed_sql
        return {"current_sql": repaired}

    prompt = (
        f"{SQL_FIXER_PROMPT}\n\n"
        f"DATABASE SCHEMA:\n{state.get('schema_prompt', SQL_SCHEMA_PROMPT)}\n\n"
        f"FAILED SQL:\n{failed_sql}\n\n"
        f"SQLITE ERROR:\n{error_msg}\n\n"
        f"USER QUESTION: {state.get('question')}\n"
    )
    raw = await call_llm_text(provider, prompt=prompt, model=settings.GROQ_MODEL)
    clean_sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
    if clean_sql == failed_sql:
        logger.warning(msg("sql_fixer_identical"))
        var_prompt = f"{prompt}\n\nIMPORTANT: {msg('sql_fixer_variation_prompt')}"
        raw = await call_llm_text(provider, prompt=var_prompt, model=settings.GROQ_MODEL)
        clean_sql = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()

    return {"current_sql": clean_sql}


async def broaden_query_node(
    state: SQLSubState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Relax narrow query filters when zero rows are returned on the first pass."""
    emit_status(writer, "sql_agent", "running", msg("sql_broadening_query"))
    sql = state.get("current_sql") or ""

    # Relax secondary WHERE/AND filter clause to broaden search results
    broadened_sql = re.sub(
        r"\s+AND\s+[\w\.]+\s+(?:LIKE|=)\s*'[^']+'(?:\s+COLLATE\s+\w+)?",
        "",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )

    return {
        "current_sql": broadened_sql.strip(),
        "broadened": True,
    }


async def finish_node(state: SQLSubState, writer: StreamWriter | None = None) -> dict[str, Any]:
    """Finalize successful SQL sub-graph execution."""
    return {"success": True}


async def give_up_node(state: SQLSubState, writer: StreamWriter | None = None) -> dict[str, Any]:
    """Handle retry exhaustion or failure without crashing."""
    emit_status(writer, "sql_agent", "done", msg("sql_retry_limit"))
    return {
        "success": False,
        "table": state.get("table") or TableResult(columns=[], rows=[], row_count=0),
        "empty_db": True,
    }
