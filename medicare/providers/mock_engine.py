"""Deterministic Mock LLM Engine and Scripted test double for testing and offline execution."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from medicare.config import settings
from medicare.config_loader import get_app_config, get_intent_words, get_prompt, msg
from medicare.domain.models import ChatMessage, ToolCallDescriptor
from medicare.domain.protocols import ModelProviderProtocol
from medicare.tools.db_tools import get_known_catalog, get_live_schema

logger = logging.getLogger(__name__)


class ScriptedProvider(ModelProviderProtocol):
    """Test double providing scripted sequential responses for deterministic verification."""

    def __init__(self, responses: list[str | ChatMessage | dict[str, Any]]) -> None:
        self.responses: list[str | ChatMessage | dict[str, Any]] = list(responses)
        self.call_count: int = 0
        self.recorded_messages: list[Any] = []

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str = "scripted-test",
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> ChatMessage:
        self.call_count += 1
        self.recorded_messages.append(messages)
        if not self.responses:
            return ChatMessage(type="ai", content="No more scripted responses.")

        resp = self.responses.pop(0)
        if isinstance(resp, ChatMessage):
            return resp
        if isinstance(resp, dict):
            content = resp.get("content") or ""
            return ChatMessage(type="ai", content=content, response_metadata={"model": model})
        return ChatMessage(type="ai", content=resp, response_metadata={"model": model})

    async def stream_tokens(
        self,
        messages: list[ChatMessage],
        model: str = "scripted-test",
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        msg = await self.generate(messages, model, tools)
        tokens = re.split(r"(\s+)", msg.content)
        for t in tokens:
            if t:
                yield t

    async def chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        self.call_count += 1
        self.recorded_messages.append(messages)
        if not self.responses:
            return {"content": "No more scripted responses.", "tool_calls": []}

        resp = self.responses.pop(0)
        if isinstance(resp, dict):
            return {
                "content": resp.get("content"),
                "tool_calls": resp.get("tool_calls", []),
            }
        if isinstance(resp, ChatMessage):
            tcs = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls
            ]
            return {"content": resp.content, "tool_calls": tcs}
        return {"content": str(resp), "tool_calls": []}


class MockModelEngine(ModelProviderProtocol):
    """Deterministic model engine simulating standard tools and MediCare Navigator pipeline."""

    def __init__(self) -> None:
        self._demo_failed_once: bool = False

    def reset_demo_state(self) -> None:
        """Reset demo retry state."""
        self._demo_failed_once = False

    def _handle_medicare_router(self, text: str) -> str:
        """Dynamic intent classification and entity resolution for MediCare Navigator."""
        text_lower = text.lower()
        intent_cfg = get_intent_words()
        greetings = set(intent_cfg.get("conversational_greetings", []))
        patterns = intent_cfg.get("conversational_patterns", [])
        policy_indicators = intent_cfg.get("policy_indicators", [])
        data_indicators = intent_cfg.get("data_indicators", [])

        has_policy = any(k in text_lower for k in policy_indicators)
        has_data = any(k in text_lower for k in data_indicators)

        is_greeting = (
            any(g == text_lower or text_lower.startswith(g + " ") for g in greetings)
            or any(re.search(p, text_lower) for p in patterns)
            or (not has_policy and not has_data)
        )

        if is_greeting and not has_policy and not has_data:
            route = "conversational"
        elif has_policy and has_data:
            route = "both"
        elif has_policy:
            route = "policy_only"
        elif has_data:
            route = "data_only"
        else:
            route = "conversational"

        # Dynamically extract entities from live database catalog
        city = None
        procedure = None
        insurer = None
        cat = get_known_catalog()
        if isinstance(cat, tuple) and len(cat) == 3:
            cities_vals = list(cat[0].values())
            proc_vals = list(cat[1].values())
            ins_vals = list(cat[2].values())
        elif isinstance(cat, dict):
            cities_vals = list(cat.get("cities", []))
            proc_vals = list(cat.get("procedures", []))
            ins_vals = list(cat.get("insurers", []))
        else:
            cities_vals, proc_vals, ins_vals = [], [], []

        for c_val in sorted(cities_vals, key=len, reverse=True):
            if c_val and re.search(r"\b" + re.escape(c_val.lower()) + r"\b", text_lower):
                city = c_val
                break

        for p_val in sorted(proc_vals, key=len, reverse=True):
            if p_val and re.search(r"\b" + re.escape(p_val.lower()) + r"\b", text_lower):
                procedure = p_val
                break

        for ins_val in sorted(ins_vals, key=len, reverse=True):
            if ins_val and re.search(r"\b" + re.escape(ins_val.lower()) + r"\b", text_lower):
                insurer = ins_val
                break

        return json.dumps(
            {
                "route": route,
                "entities": {
                    "city": city,
                    "procedure": procedure,
                    "insurer": insurer,
                },
            }
        )

    def _handle_medicare_sql_generator(self, text: str) -> str:
        """Dynamic SQL generation inspecting live database entities."""
        if "USER QUESTION:" in text:
            text = text.split("USER QUESTION:")[-1]
        text_lower = text.lower()
        mq = get_app_config().get("mock_queries", {})

        # If MEDICARE_DEMO_FAIL_FIRST is set and not yet failed once, deliberately output invalid column
        if getattr(settings, "MEDICARE_DEMO_FAIL_FIRST", False) and not self._demo_failed_once:
            self._demo_failed_once = True
            return mq.get("demo_fail_sql", "")

        # Check if alternative schema is active (e.g. books)
        schema = get_live_schema()
        if "books" in schema:
            return "SELECT title, author, price FROM books ORDER BY price ASC LIMIT 50"

        # Dynamically match against live catalog
        where_clauses = ["1=1"]
        cat = get_known_catalog()
        if isinstance(cat, tuple) and len(cat) == 3:
            cities_vals = list(cat[0].values())
            proc_vals = list(cat[1].values())
            ins_vals = list(cat[2].values())
        elif isinstance(cat, dict):
            cities_vals = list(cat.get("cities", []))
            proc_vals = list(cat.get("procedures", []))
            ins_vals = list(cat.get("insurers", []))
        else:
            cities_vals, proc_vals, ins_vals = [], [], []

        w_city = mq.get("where_city", "")
        w_proc = mq.get("where_procedure", "")
        w_ins = mq.get("where_insurer", "")
        w_cash = mq.get("where_accepted", "")

        for c_val in sorted(cities_vals, key=len, reverse=True):
            if c_val and re.search(r"\b" + re.escape(c_val.lower()) + r"\b", text_lower):
                if w_city:
                    where_clauses.append(w_city.format(val=c_val))
                break

        for p_val in sorted(proc_vals, key=len, reverse=True):
            if p_val and re.search(r"\b" + re.escape(p_val.lower()) + r"\b", text_lower):
                if w_proc:
                    where_clauses.append(w_proc.format(val=p_val))
                break

        for ins_val in sorted(ins_vals, key=len, reverse=True):
            if ins_val and re.search(r"\b" + re.escape(ins_val.lower()) + r"\b", text_lower):
                if w_ins:
                    where_clauses.append(w_ins.format(val=ins_val))
                if w_cash:
                    where_clauses.append(w_cash)
                break

        is_count = any(
            k in text_lower
            for k in ["how many", "count", "how much hospitals", "number of hospitals"]
        )
        where_sql = " AND ".join(where_clauses)
        if is_count:
            count_template = mq.get(
                "hospitals_count_sql",
                "SELECT count(*) AS hospital_count FROM hospitals h WHERE {where_sql}",
            )
            return count_template.format(where_sql=where_sql)
        template = mq.get("hospitals_sql", "")
        return template.format(where_sql=where_sql)

    def _handle_medicare_sql_fixer(self, text: str) -> str:
        """Fix SQL query by resolving invalid column or syntax error."""
        fixed = text
        mq = get_app_config().get("mock_queries", {})
        inv_col = mq.get("fix_invalid_col", "")
        tar_col = mq.get("fix_target_col", "")
        if inv_col and tar_col and inv_col in fixed:
            fixed = fixed.replace(inv_col, tar_col)
        select_match = re.search(r"SELECT\s+.*", fixed, re.DOTALL | re.IGNORECASE)
        if select_match:
            clean_sql = select_match.group(0).strip()
            clean_sql = re.sub(r"```[a-z]*", "", clean_sql).replace("```", "").strip()
            if inv_col and tar_col and inv_col in clean_sql:
                clean_sql = clean_sql.replace(inv_col, tar_col)
            return clean_sql

        return mq.get("hospitals_sql", "").format(where_sql="1=1")

    def _handle_medicare_synthesizer(self, text: str) -> str:
        """Deterministic synthesis of healthcare recommendation."""
        proc = "the requested procedure"
        city = "the specified location"
        summary_text = msg("fallback_summary", procedure=proc, city=city)
        sec1 = f"{msg('fallback_heading_summary')}\n\n{summary_text}"
        sec2 = f"{msg('fallback_heading_caveats')}\n\n{msg('disclaimer_consult_provider')}"
        return f"{sec1}\n\n{sec2}"

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> ChatMessage:
        model = model or settings.FALLBACK_MODEL
        if not messages:
            return ChatMessage(type="ai", content="Hello! How can I assist you today?")

        last_msg = messages[-1]
        text = last_msg.content.strip()

        combined_text = "\n".join(m.content for m in messages)

        if "CONVERSATIONAL" in combined_text or "conversational" in combined_text:
            return ChatMessage(
                type="ai",
                content=msg("conversational_welcome"),
                response_metadata={"model": model, "finish_reason": "stop"},
            )

        router_prompt = get_prompt("router")
        if "Router for MediCare" in combined_text or (
            router_prompt and router_prompt in combined_text
        ):
            return ChatMessage(
                type="ai",
                content=self._handle_medicare_router(text),
                response_metadata={"model": model, "finish_reason": "stop"},
            )

        sql_gen_prompt = get_prompt("sql_generator")
        if "expert SQLite query generator" in combined_text or (
            sql_gen_prompt and sql_gen_prompt in combined_text
        ):
            return ChatMessage(
                type="ai",
                content=self._handle_medicare_sql_generator(text),
                response_metadata={"model": model, "finish_reason": "stop"},
            )

        sql_fix_prompt = get_prompt("sql_fixer")
        if "self-correcting SQLite query fixer" in combined_text or (
            sql_fix_prompt and sql_fix_prompt in combined_text
        ):
            return ChatMessage(
                type="ai",
                content=self._handle_medicare_sql_fixer(text),
                response_metadata={"model": model, "finish_reason": "stop"},
            )

        synth_prompt = get_prompt("synthesizer")
        if "synthesizer" in combined_text.lower() or (
            synth_prompt and synth_prompt in combined_text
        ):
            return ChatMessage(
                type="ai",
                content=self._handle_medicare_synthesizer(text),
                response_metadata={"model": model, "finish_reason": "stop"},
            )

        if last_msg.type == "tool":
            return ChatMessage(
                type="ai",
                content=f"Based on the retrieved tool data:\n\n{last_msg.content}\n\nSynthesized solution is complete.",
                response_metadata={"model": model, "finish_reason": "stop"},
            )

        if tools:
            tool_names = [t.get("function", {}).get("name") for t in tools]

            if "calculator" in tool_names and any(
                op in text.lower()
                for op in ["+", "-", "*", "/", "sqrt", "calculate", "math", "evaluate"]
            ):
                expr_match = re.search(r"[\d\.\s\+\-\*\/\(\)\^%]+", text)
                expr = expr_match.group(0).strip() if expr_match else "42 * 2"
                return ChatMessage(
                    type="ai",
                    content="Computing mathematical expression...",
                    tool_calls=[
                        ToolCallDescriptor(name="calculator", arguments={"expression": expr})
                    ],
                    response_metadata={"model": model, "finish_reason": "tool_calls"},
                )

            if "web_search" in tool_names and any(
                k in text.lower()
                for k in ["search", "who is", "what is", "news", "faang", "headcount"]
            ):
                return ChatMessage(
                    type="ai",
                    content="Searching web...",
                    tool_calls=[
                        ToolCallDescriptor(name="web_search", arguments={"query": last_msg.content})
                    ],
                    response_metadata={"model": model, "finish_reason": "tool_calls"},
                )

            if "weather" in tool_names and "weather" in text.lower():
                loc = (
                    "Tokyo"
                    if "tokyo" in text.lower()
                    else ("Paris" if "paris" in text.lower() else "New York")
                )
                return ChatMessage(
                    type="ai",
                    content=f"Checking weather for {loc}...",
                    tool_calls=[ToolCallDescriptor(name="weather", arguments={"location": loc})],
                    response_metadata={"model": model, "finish_reason": "tool_calls"},
                )

            if "vector_rag" in tool_names and any(
                k in text.lower()
                for k in ["policy", "handbook", "expense", "remote work", "laptop"]
            ):
                return ChatMessage(
                    type="ai",
                    content="Searching policy database...",
                    tool_calls=[
                        ToolCallDescriptor(name="vector_rag", arguments={"query": last_msg.content})
                    ],
                    response_metadata={"model": model, "finish_reason": "tool_calls"},
                )

            if "cloud_kb_search" in tool_names and any(
                k in text.lower() for k in ["cloud", "architecture", "disaster recovery"]
            ):
                return ChatMessage(
                    type="ai",
                    content="Querying cloud knowledge base...",
                    tool_calls=[
                        ToolCallDescriptor(
                            name="cloud_kb_search", arguments={"query": last_msg.content}
                        )
                    ],
                    response_metadata={"model": model, "finish_reason": "tool_calls"},
                )

        return ChatMessage(
            type="ai",
            content=f"Response from {model}: I have processed your request '{last_msg.content}'.",
            response_metadata={"model": model, "finish_reason": "stop"},
        )

    async def stream_tokens(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        full_msg = await self.generate(messages, model, tools)
        tokens = re.split(r"(\s+)", full_msg.content)
        for t in tokens:
            if t:
                await asyncio.sleep(0.005)
                yield t

    async def chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Simulate function-calling agent turns for offline testing."""
        tool_names = set()
        if tools:
            for t in tools:
                if isinstance(t, dict):
                    fn = t.get("function", {})
                    name = fn.get("name") or t.get("name")
                    if name:
                        tool_names.add(name)

        tool_call_ids_returned = set()
        last_user_content = ""
        for m in messages:
            if isinstance(m, dict):
                if m.get("role") == "user":
                    last_user_content = m.get("content", "")
                if m.get("role") == "tool":
                    tool_call_ids_returned.add(m.get("tool_call_id"))
            elif isinstance(m, ChatMessage):
                if m.type == "human":
                    last_user_content = m.content
                if m.type == "tool":
                    tool_call_ids_returned.add(m.tool_call_id)

        # SQL worker simulation
        if "run_sql" in tool_names:
            if "get_schema" in tool_names and "call_schema" not in tool_call_ids_returned:
                return {
                    "content": None,
                    "tool_calls": [{"id": "call_schema", "name": "get_schema", "arguments": {}}],
                }
            if "lookup_values" in tool_names and "call_lookup" not in tool_call_ids_returned:
                schema_dict = get_live_schema()
                first_t = next(iter(schema_dict.keys()), "")
                first_c = (
                    schema_dict[first_t]["columns"][0]
                    if first_t and schema_dict[first_t].get("columns")
                    else ""
                )
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_lookup",
                            "name": "lookup_values",
                            "arguments": {
                                "table": first_t,
                                "column": first_c,
                                "text": last_user_content[:10],
                            },
                        }
                    ],
                }
            if "call_sql" not in tool_call_ids_returned:
                sql = self._handle_medicare_sql_generator(last_user_content)
                return {
                    "content": None,
                    "tool_calls": [
                        {"id": "call_sql", "name": "run_sql", "arguments": {"query": sql}}
                    ],
                }
            return {
                "content": f"Retrieved data for: {last_user_content}",
                "tool_calls": [],
            }

        # Policy worker simulation
        if "search_documents" in tool_names:
            if (
                "list_document_filters" in tool_names
                and "call_filters" not in tool_call_ids_returned
            ):
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_filters",
                            "name": "list_document_filters",
                            "arguments": {},
                        }
                    ],
                }
            if "call_search" not in tool_call_ids_returned:
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_search",
                            "name": "search_documents",
                            "arguments": {"query": last_user_content},
                        }
                    ],
                }
            return {
                "content": f"Retrieved policy clauses for: {last_user_content}",
                "tool_calls": [],
            }

        # Fallback to standard generation
        chat_msgs: list[ChatMessage] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                chat_msgs.append(m)
            elif isinstance(m, dict):
                m_type = (
                    "ai"
                    if m.get("role") == "assistant"
                    else ("human" if m.get("role") == "user" else "custom")
                )
                chat_msgs.append(ChatMessage(type=m_type, content=m.get("content", "")))
        res_msg = await self.generate(
            chat_msgs, model=model or settings.FALLBACK_MODEL, tools=tools, temperature=temperature
        )
        return {"content": res_msg.content, "tool_calls": []}
