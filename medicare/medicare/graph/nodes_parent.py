"""Parent graph execution nodes coordinating supervisor, workers, synthesis, and verification."""

import logging
import time
from typing import Any

from langgraph.types import StreamWriter

from medicare.config import settings
from medicare.config_loader import msg
from medicare.domain.protocols import MemoryStoreProtocol, ModelProviderProtocol
from medicare.medicare.chart import build_chart_spec
from medicare.medicare.graph.events import emit_status, emit_token
from medicare.medicare.graph.routing import (
    _get_known_catalog,
    canonicalize_entities,
    generate_scoping_followups,
    is_underspecified_comparison,
    rules_route,
)
from medicare.medicare.graph.state import (
    GuardrailOutcome,
    NavigatorState,
    PolicyAgentResult,
    SQLAgentResult,
    SupervisorPlan,
    TraceEntry,
)
from medicare.medicare.graph.verify import build_deterministic_fallback, verify_grounding
from medicare.medicare.prompts import (
    CONVERSATIONAL_PROMPT,
    SUPERVISOR_PROMPT,
    SYNTHESIZER_PROMPT,
    VERIFIER_REPAIR_PROMPT,
    call_json,
    call_llm_text,
)
from medicare.security.guardrails import check_medicare_guardrails
from medicare.tools.sql_query import SQLiteQueryTool

logger = logging.getLogger(__name__)


async def guardrail_node(
    state: NavigatorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Evaluate pre-execution security, clinical emergencies, PII, and injection guardrails."""
    t0 = time.perf_counter()
    question = state.get("question", "")

    gr = check_medicare_guardrails(question)
    ms = (time.perf_counter() - t0) * 1000.0

    if gr.blocked:
        emit_status(
            writer,
            "guardrail",
            "blocked",
            gr.message or "Query blocked by safety policy.",
            category=gr.category,
        )
        return {
            "guardrail": GuardrailOutcome(
                blocked=True,
                category=gr.category,
                safe_message=gr.message,
                redacted_question=gr.redacted_prompt,
            ),
            "trace": [TraceEntry(node="guardrail", status="blocked", ms=ms, note=gr.category)],
            "timings": {"guardrail": ms},
        }

    emit_status(writer, "guardrail", "done", "Safety guardrail evaluation passed.")
    soft_flags = ["medical_disclaimer"] if gr.has_medical_advice_boundary else []
    return {
        "question": gr.redacted_prompt,
        "guardrail": GuardrailOutcome(
            blocked=False,
            redacted_question=gr.redacted_prompt,
            soft_flags=soft_flags,
        ),
        "trace": [TraceEntry(node="guardrail", status="done", ms=ms)],
        "timings": {"guardrail": ms},
    }


async def blocked_response_node(
    state: NavigatorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Emit tokens and terminate stream when guardrail blocks execution."""
    outcome = state.get("guardrail")
    msg = outcome.safe_message if outcome else "Request blocked by security guardrails."
    emit_token(writer, msg)
    return {
        "answer": msg,
        "chart": None,
    }


async def supervisor_node(
    state: NavigatorState,
    provider: ModelProviderProtocol,
    memory_store: MemoryStoreProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Evaluate intent, extract & canonicalize entities, and plan worker execution."""
    t0 = time.perf_counter()
    emit_status(writer, "supervisor", "running", "Planning query execution and routing...")

    user_id = state.get("user_id") or "default_user"
    question = state.get("question", "")

    # Load long-term user preferences
    prior_prefs: dict[str, Any] = {}
    try:
        mem_data = await memory_store.get((user_id,), "medicare_prefs")
        if isinstance(mem_data, dict):
            prior_prefs = mem_data
    except Exception:
        pass

    # Check previous turns for carry-over
    history = state.get("history", [])
    if history:
        for turn in reversed(history[-4:]):
            content = turn.get("content", "").lower()
            # Inherit prior entities if found in history dynamically from live catalog
            cities_map, procs_map, ins_map = _get_known_catalog()
            if "city" not in prior_prefs:
                for c_key, c_val in cities_map.items():
                    if c_key in content:
                        prior_prefs["city"] = c_val
                        break
            if "procedure" not in prior_prefs:
                for p_key, p_val in procs_map.items():
                    if p_key in content:
                        prior_prefs["procedure"] = p_val
                        break
            if "insurer" not in prior_prefs:
                for i_key, i_val in ins_map.items():
                    if i_key in content:
                        prior_prefs["insurer"] = i_val
                        break

    plan: SupervisorPlan | None = None

    # LLM Planning Path
    if (
        settings.SUPERVISOR_USE_LLM
        and not settings.USE_MOCK_MODELS
        and provider.__class__.__name__ != "MockModelEngine"
    ):
        prompt = (
            f"{SUPERVISOR_PROMPT}\n\nUSER QUERY: {question}\nSTORED PREFERENCES: {prior_prefs}\n"
        )
        try:
            plan = await call_json(SupervisorPlan, prompt, provider, model=settings.GROQ_MODEL)
        except Exception as e:
            logger.warning(f"Supervisor LLM call failed: {e}. Falling back to rules router.")

    # Rules Router Fallback
    active_db = SQLiteQueryTool.ACTIVE_DB_PATH
    rules_plan = rules_route(question, prior_prefs=prior_prefs, db_path=active_db)

    if plan is None:
        plan = rules_plan
    else:
        # Cross-check: If LLM says conversational but domain keywords are present or low confidence
        if (
            plan.route == "conversational" and rules_plan.route != "conversational"
        ) or plan.confidence < settings.SUPERVISOR_MIN_CONFIDENCE:
            logger.info(msg("supervisor_override"))
            plan = rules_plan

    # Canonicalize extracted entities
    plan.entities = canonicalize_entities(plan.entities, db_path=active_db)

    # Check clarification sanity: never clarify twice in a row
    if plan.route == "clarify" and history:
        last_turn = history[-1]
        if last_turn.get("role") == "assistant" and "?" in last_turn.get("content", ""):
            plan.route = "both"
            plan.needs_clarification = False

    # Emit status and mark skipped nodes
    emit_status(writer, "supervisor", "done", f"Plan finalized: route='{plan.route}'.")
    if plan.route == "data_only":
        emit_status(writer, "policy_agent", "skipped", msg("policy_skipped_data_only"))
    elif plan.route == "policy_only":
        emit_status(writer, "sql_agent", "skipped", msg("sql_skipped_policy_only"))
    elif plan.route in ("conversational", "clarify"):
        emit_status(writer, "sql_agent", "skipped", "Hospital SQL skipped.")
        emit_status(writer, "policy_agent", "skipped", "Policy Agent skipped.")

    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "plan": plan,
        "trace": [TraceEntry(node="supervisor", status="done", ms=ms, note=plan.route)],
        "timings": {"supervisor": ms},
    }


async def conversational_node(
    state: NavigatorState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Generate friendly introductory response for casual greetings without tools."""
    emit_status(writer, "synthesizer", "running", "Generating conversational greeting...")

    if settings.USE_MOCK_MODELS or provider.__class__.__name__ == "MockModelEngine":
        answer = msg("conversational_welcome")
    else:
        answer = await call_llm_text(
            provider,
            prompt=f"{CONVERSATIONAL_PROMPT}\n\nUSER: {state.get('question')}",
            model=settings.GROQ_MODEL,
        )

    # Stream answer tokens
    for word in answer.split(" "):
        emit_token(writer, word + " ")

    return {
        "answer": answer,
        "chart": None,
    }


async def clarify_node(
    state: NavigatorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Ask user for clarification when inquiry is fundamentally ambiguous."""
    plan = state.get("plan")
    entities = plan.entities if plan else {}
    q = (
        plan.clarification_question
        if plan and plan.clarification_question
        else msg("clarification_default")
    )
    followups = generate_scoping_followups(entities)
    emit_token(writer, q)
    return {
        "answer": q,
        "chart": None,
        "followups": followups,
    }


async def sql_worker_node(
    state: NavigatorState,
    sql_graph: Any,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Execute Hospital SQL sub-graph and forward progress events to parent stream."""
    t0 = time.perf_counter()
    sub_input = {
        "question": state.get("question", ""),
        "plan": state.get("plan"),
        "attempts": [],
        "retry_count": 0,
    }

    final_sub_state: dict[str, Any] = {}
    async for mode, chunk in sql_graph.astream(sub_input, stream_mode=["custom", "values"]):
        if mode == "custom":
            if writer:
                writer(chunk)
        elif mode == "values":
            final_sub_state = chunk

    res = SQLAgentResult(
        attempts=final_sub_state.get("attempts", []),
        table=final_sub_state.get("table"),
        success=final_sub_state.get("success", False),
        broadened=final_sub_state.get("broadened", False),
        error_summary=final_sub_state.get("error_summary"),
        empty_db=final_sub_state.get("empty_db", False),
        final_sql=final_sub_state.get("final_sql"),
    )

    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "sql_result": res,
        "trace": [TraceEntry(node="sql_agent", status="done" if res.success else "error", ms=ms)],
        "timings": {"sql_agent": ms},
    }


async def policy_worker_node(
    state: NavigatorState,
    policy_graph: Any,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Execute Policy RAG sub-graph and forward progress events to parent stream."""
    t0 = time.perf_counter()
    sub_input = {
        "question": state.get("question", ""),
        "plan": state.get("plan"),
        "user_id": state.get("user_id"),
        "doc_scope": state.get("doc_scope", "both"),
    }

    final_sub_state: dict[str, Any] = {}
    async for mode, chunk in policy_graph.astream(sub_input, stream_mode=["custom", "values"]):
        if mode == "custom":
            if writer:
                writer(chunk)
        elif mode == "values":
            final_sub_state = chunk

    res = PolicyAgentResult(
        citations=final_sub_state.get("citations", []),
        rewrites_used=final_sub_state.get("rewrites_used", 0),
        insurer_fallback=final_sub_state.get("insurer_fallback", False),
        no_evidence=final_sub_state.get("no_evidence", False),
        index_empty=final_sub_state.get("index_empty", False),
    )

    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "policy_result": res,
        "trace": [TraceEntry(node="policy_agent", status="done", ms=ms)],
        "timings": {"policy_agent": ms},
    }


async def synthesizer_node(
    state: NavigatorState,
    provider: ModelProviderProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Synthesize evidence pack into structured recommendation and stream tokens."""
    t0 = time.perf_counter()
    emit_status(writer, "synthesizer", "running", msg("synthesizing_recommendations"))

    plan = state.get("plan")
    sql_res = state.get("sql_result")
    policy_res = state.get("policy_result")
    regenerations = state.get("regenerations", 0)

    entities = plan.entities if plan else {}
    row_count = len(sql_res.table.rows) if sql_res and sql_res.table and sql_res.table.rows else 0
    q_text = state.get("question", "")
    is_underspecified = is_underspecified_comparison(q_text, entities, candidate_count=row_count)

    # Build chart if table has >= 2 rows and query is not an underspecified scoping query
    chart_spec = None
    if not is_underspecified and sql_res and sql_res.table and sql_res.table.row_count >= 2:
        chart_spec = build_chart_spec(sql_res.table)

    followups: list[str] = []
    if is_underspecified:
        followups = generate_scoping_followups(entities)
    elif sql_res and sql_res.table and sql_res.table.rows:
        city = entities.get("city") or "your city"
        followups = [
            msg("chip_lowest_cost", city=city),
            msg("chip_shortest_wait", city=city),
            msg("chip_check_insurance"),
            msg("chip_show_full_table"),
        ]

    # In mock mode or when broad scoping is required: generate verified template matching evidence
    if (
        is_underspecified
        or settings.USE_MOCK_MODELS
        or provider.__class__.__name__ == "MockModelEngine"
    ):
        answer = build_deterministic_fallback(
            plan=plan or SupervisorPlan(),
            sql_result=sql_res,
            policy_result=policy_res,
        )
    else:
        # Construct verified data context for live model
        evidence_lines = []
        if sql_res and sql_res.table and sql_res.table.rows:
            evidence_lines.append(f"HOSPITAL DATA ({len(sql_res.table.rows)} items):")
            for r in sql_res.table.rows[:30]:
                evidence_lines.append(str(r))
        elif sql_res and sql_res.empty_db:
            evidence_lines.append("HOSPITAL DATA: None (0 items found).")

        if policy_res and policy_res.citations:
            evidence_lines.append(f"POLICY CITATIONS ({len(policy_res.citations)} items):")
            for c in policy_res.citations:
                evidence_lines.append(
                    f"<<<DOC id={c.cite_id} source='{c.source}'>>> {c.text} <<<END>>>"
                )
        elif policy_res and policy_res.no_evidence:
            evidence_lines.append(f"POLICY CITATIONS: {msg('no_policy_evidence')}")

        evidence_text = "\n".join(evidence_lines)

        if regenerations > 0:
            report = state.get("grounding")
            issues_str = "\n".join(report.issues) if report else "Numeric claims ungrounded"
            prompt = VERIFIER_REPAIR_PROMPT.format(
                issues=issues_str,
                evidence=evidence_text,
                original_draft=state.get("answer", ""),
            )
        else:
            prompt = (
                f"{SYNTHESIZER_PROMPT}\n\n"
                f"USER QUESTION: {state.get('question')}\n\n"
                f"VERIFIED CLINICAL DATA:\n{evidence_text}\n"
            )

        try:
            answer = await call_llm_text(provider, prompt=prompt, model=settings.GROQ_MODEL)
        except Exception as e:
            logger.warning(msg("synthesizer_llm_unavailable", error=str(e)))
            citations = policy_res.citations if policy_res else []
            fallback_lines = [
                msg("provider_offline_notice"),
                "",
            ]
            if citations:
                fallback_lines.append(msg("policy_excerpts_heading"))
                for c in citations:
                    fallback_lines.append(
                        f"- **[{c.cite_id}] {c.source}** ({c.section}):\n  > {c.text.strip()}\n"
                    )
            else:
                fallback_lines.append(msg("no_policy_evidence"))
            answer = "\n".join(fallback_lines)

    # Emit tokens over SSE custom stream
    for word in answer.split(" "):
        emit_token(writer, word + " ")

    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "answer": answer,
        "chart": chart_spec,
        "followups": followups,
        "trace": [TraceEntry(node="synthesizer", status="done", ms=ms)],
        "timings": {"synthesizer": ms},
    }


async def verifier_node(
    state: NavigatorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Verify numeric claims, citations, and hospital entities against evidence."""
    t0 = time.perf_counter()
    emit_status(writer, "verifier", "running", msg("verifying_grounding"))

    answer = state.get("answer", "")
    sql_res = state.get("sql_result")
    policy_res = state.get("policy_result")
    table = sql_res.table if sql_res else None
    citations = policy_res.citations if policy_res else []

    report = verify_grounding(answer=answer, table=table, citations=citations)

    ms = (time.perf_counter() - t0) * 1000.0
    if report.passed:
        emit_status(writer, "verifier", "done", msg("grounding_verified"))
        return {
            "grounding": report,
            "trace": [TraceEntry(node="verifier", status="done", ms=ms)],
            "timings": {"verifier": ms},
        }

    # If verification failed
    regenerations = state.get("regenerations", 0)
    if regenerations < settings.VERIFIER_MAX_REGENERATIONS:
        emit_status(
            writer,
            "verifier",
            "retry",
            f"Grounding issues detected ({len(report.issues)} items). Regenerating answer...",
        )
        report.regenerated = True
        return {
            "grounding": report,
            "regenerations": regenerations + 1,
            "trace": [TraceEntry(node="verifier", status="retry", ms=ms, note="repair")],
            "timings": {"verifier": ms},
        }

    # Regenerations exhausted -> apply deterministic fallback
    emit_status(
        writer,
        "verifier",
        "fallback",
        msg("grounding_exhausted_fallback"),
    )
    fallback_answer = build_deterministic_fallback(
        plan=state.get("plan") or SupervisorPlan(),
        sql_result=sql_res,
        policy_result=policy_res,
    )
    report.fallback_used = True
    return {
        "answer": fallback_answer,
        "grounding": report,
        "trace": [TraceEntry(node="verifier", status="fallback", ms=ms)],
        "timings": {"verifier": ms},
    }


async def finalize_node(
    state: NavigatorState,
    memory_store: MemoryStoreProtocol,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Persist non-PII user preferences into long-term memory."""
    t0 = time.perf_counter()
    user_id = state.get("user_id") or "default_user"
    plan = state.get("plan")

    if plan and plan.entities:
        non_pii_prefs: dict[str, Any] = {}
        for k in ["city", "procedure", "insurer"]:
            if plan.entities.get(k):
                non_pii_prefs[k] = plan.entities[k]

        if non_pii_prefs:
            try:
                await memory_store.put((user_id,), "medicare_prefs", non_pii_prefs)
            except Exception as e:
                logger.warning(f"Could not persist user preferences: {e}")

    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "trace": [TraceEntry(node="finalize", status="done", ms=ms)],
        "timings": {"finalize": ms},
    }
