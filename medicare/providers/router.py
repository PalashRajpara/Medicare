"""Provider router selecting between live LLM integrations (Groq) and mock engine."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from medicare.config import settings
from medicare.domain.errors import ProviderUnavailableError
from medicare.domain.models import ChatMessage
from medicare.domain.protocols import ModelProviderProtocol
from medicare.providers.mock_engine import MockModelEngine

logger = logging.getLogger(__name__)

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


def _format_chat_messages(
    messages: list[ChatMessage | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Format domain ChatMessages or dicts into OpenAI/Groq wire format."""
    formatted: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            formatted.append(m)
        elif isinstance(m, ChatMessage):
            role = "assistant" if m.type == "ai" else ("user" if m.type == "human" else m.type)
            msg_dict: dict[str, Any] = {"role": role, "content": m.content}
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": (
                                json.dumps(tc.arguments)
                                if isinstance(tc.arguments, dict)
                                else str(tc.arguments)
                            ),
                        },
                    }
                    for tc in m.tool_calls
                ]
            formatted.append(msg_dict)
    return formatted


class LiveGroqProvider(ModelProviderProtocol):
    """Live Groq LLM integration with exponential backoff and rate limit handling."""

    def __init__(self, api_key: str, default_model: str = "llama-3.3-70b-versatile") -> None:
        self.api_key = api_key
        self.default_model = default_model

    def _resolve_model(self, requested_model: str) -> str:
        if requested_model in ("groq-llama-3", "groq", "llama3"):
            return getattr(settings, "GROQ_MODEL", self.default_model)
        return getattr(settings, "GROQ_MODEL", self.default_model)

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> ChatMessage:
        target_model = self._resolve_model(model)
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [
                {
                    "role": (
                        "assistant" if m.type == "ai" else ("user" if m.type == "human" else m.type)
                    ),
                    "content": m.content,
                }
                for m in messages
            ],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Exponential backoff up to 3 retries
        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(GROQ_ENDPOINT, headers=headers, json=payload)
                    if resp.status_code == 429:
                        wait_sec = 2**attempt
                        logger.warning(
                            "Groq rate limited (429). Retrying in %ss (attempt %s/3)...",
                            wait_sec,
                            attempt,
                        )
                        await asyncio.sleep(wait_sec)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    choice = data["choices"][0]
                    content = choice["message"]["content"]
                    return ChatMessage(
                        type="ai",
                        content=content,
                        response_metadata={"model": target_model, "provider": "groq"},
                    )
            except httpx.HTTPStatusError as e:
                logger.error("Groq HTTP error %s: %s", e.response.status_code, e.response.text)
                if attempt == 3:
                    raise ProviderUnavailableError(
                        f"Groq API error ({e.response.status_code})"
                    ) from e
            except Exception as e:
                logger.error("Groq connection failure: %s", e)
                if attempt == 3:
                    raise ProviderUnavailableError(f"Failed to communicate with Groq: {e}") from e
                await asyncio.sleep(1.0 * attempt)

        raise ProviderUnavailableError("Groq retries exhausted.")

    async def stream_tokens(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        target_model = self._resolve_model(model)
        payload = {
            "model": target_model,
            "messages": [
                {
                    "role": (
                        "assistant" if m.type == "ai" else ("user" if m.type == "human" else m.type)
                    ),
                    "content": m.content,
                }
                for m in messages
            ],
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with (
                httpx.AsyncClient(timeout=45.0) as client,
                client.stream("POST", GROQ_ENDPOINT, headers=headers, json=payload) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    chunk_str = line[6:].strip()
                    if chunk_str == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(chunk_str)
                        delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning("Groq stream failed (%s), yielding error token", e)
            yield f"\n[Provider error: {e}]"

    async def chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate response with structured tool calls {content, tool_calls}."""
        target_model = self._resolve_model(model or "")
        formatted_msgs = _format_chat_messages(messages)
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": formatted_msgs,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(GROQ_ENDPOINT, headers=headers, json=payload)
                    if resp.status_code == 429:
                        wait_sec = 2**attempt
                        logger.warning("Groq rate limited (429). Retrying in %ss...", wait_sec)
                        await asyncio.sleep(wait_sec)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    choice = data["choices"][0]["message"]
                    content = choice.get("content")
                    raw_tool_calls = choice.get("tool_calls") or []

                    parsed_tool_calls: list[dict[str, Any]] = []
                    for tc in raw_tool_calls:
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", "{}")
                        if isinstance(raw_args, str):
                            try:
                                args = json.loads(raw_args)
                            except json.JSONDecodeError as err:
                                # Safe error recovery for malformed arguments
                                args = {
                                    "_raw_arguments": raw_args,
                                    "_error": f"JSONDecodeError: {err}",
                                }
                        elif isinstance(raw_args, dict):
                            args = raw_args
                        else:
                            args = {"_value": raw_args}

                        parsed_tool_calls.append(
                            {
                                "id": tc.get("id"),
                                "name": fn.get("name"),
                                "arguments": args,
                            }
                        )

                    return {
                        "content": content,
                        "tool_calls": parsed_tool_calls,
                        "raw_message": choice,
                    }
            except httpx.HTTPStatusError as e:
                logger.error("Groq HTTP error %s: %s", e.response.status_code, e.response.text)
                if attempt == 3:
                    raise ProviderUnavailableError(
                        f"Groq API error ({e.response.status_code})"
                    ) from e
            except Exception as e:
                logger.error("Groq connection failure: %s", e)
                if attempt == 3:
                    raise ProviderUnavailableError(f"Failed to communicate with Groq: {e}") from e
                await asyncio.sleep(1.0 * attempt)

        raise ProviderUnavailableError("Groq retries exhausted.")


class ModelRouter(ModelProviderProtocol):
    """Dynamic LLM router supporting Groq live provider and mock engine fallback."""

    def __init__(self) -> None:
        self.mock_engine = MockModelEngine()
        self._groq_provider: LiveGroqProvider | None = None

    def _handle_medicare_sql_generator(self, text: str) -> str:
        return self.mock_engine._handle_medicare_sql_generator(text)

    def _handle_medicare_sql_fixer(self, text: str) -> str:
        return self.mock_engine._handle_medicare_sql_fixer(text)

    def _handle_medicare_router(self, text: str) -> str:
        return self.mock_engine._handle_medicare_router(text)

    def _handle_medicare_synthesizer(self, text: str) -> str:
        return self.mock_engine._handle_medicare_synthesizer(text)

    def _get_live_provider(self) -> LiveGroqProvider | None:
        api_key = getattr(settings, "GROQ_API_KEY", None)
        if api_key and not settings.USE_MOCK_MODELS:
            if not self._groq_provider or self._groq_provider.api_key != api_key:
                self._groq_provider = LiveGroqProvider(
                    api_key=api_key,
                    default_model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                )
            return self._groq_provider
        return None

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> ChatMessage:
        live = self._get_live_provider()
        if live:
            try:
                return await live.generate(messages, model, tools, temperature)
            except Exception as e:
                logger.warning(
                    "Live provider generation failed (%s). Falling back to mock engine.", e
                )

        return await self.mock_engine.generate(messages, model, tools, temperature)

    async def stream_tokens(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        live = self._get_live_provider()
        if live:
            try:
                async for token in live.stream_tokens(messages, model, tools):
                    yield token
                return
            except Exception as e:
                logger.warning(
                    "Live provider streaming failed (%s). Falling back to mock engine.", e
                )

        async for token in self.mock_engine.stream_tokens(messages, model, tools):
            yield token

    async def chat(
        self,
        messages: list[ChatMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        model: str | None = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        live = self._get_live_provider()
        if live:
            try:
                return await live.chat(messages, tools, tool_choice, model, temperature)
            except Exception as e:
                logger.warning("Live provider chat failed (%s). Falling back to mock engine.", e)

        return await self.mock_engine.chat(messages, tools, tool_choice, model, temperature)


router = ModelRouter()
