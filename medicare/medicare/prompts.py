"""LLM system prompts and structured JSON calling helper for MediCare Navigator."""

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from medicare.config import settings
from medicare.config_loader import get_prompt
from medicare.domain.errors import MediCareError
from medicare.domain.protocols import ModelProviderProtocol

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class JSONParsingError(MediCareError):
    """Raised when an LLM fails to output valid JSON matching the target schema."""

    def __init__(self, message: str, raw_output: str | None = None) -> None:
        super().__init__(message, status_code=500)
        self.raw_output = raw_output


# Dynamic prompt templates loaded from config/prompts/*.md
ROUTER_PROMPT = get_prompt("router")
CONVERSATIONAL_PROMPT = get_prompt("conversational")
SQL_GENERATOR_PROMPT = get_prompt("sql_generator")
SQL_FIXER_PROMPT = get_prompt("sql_fixer")
SYNTHESIZER_PROMPT = get_prompt("synthesizer")
SUPERVISOR_PROMPT = get_prompt("supervisor")
CHUNK_GRADER_PROMPT = get_prompt("chunk_grader")
QUERY_REWRITE_PROMPT = get_prompt("query_rewrite")
VERIFIER_REPAIR_PROMPT = get_prompt("verifier_repair")


def _extract_json_substring(raw: str) -> str:
    """Extract innermost or fenced JSON substring from LLM response."""
    # Check for markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # Search for first '{' and matching last '}'
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1].strip()

    return raw.strip()


async def call_llm_text(provider: Any, prompt: str, model: str | None = None) -> str:
    """Unified caller for any provider (supporting complete, generate, call)."""
    model_name = model or settings.FALLBACK_MODEL
    if hasattr(provider, "generate"):
        from medicare.domain.models import ChatMessage

        res = await provider.generate([ChatMessage(type="human", content=prompt)], model=model_name)
        return res.content if hasattr(res, "content") else str(res)
    if hasattr(provider, "complete"):
        return await provider.complete(prompt=prompt, model=model_name)
    if hasattr(provider, "call"):
        return await provider.call(prompt=prompt)
    return ""


async def call_json(
    model_cls: type[T],
    prompt: str,
    provider: ModelProviderProtocol,
    model: str | None = None,
    fallback_factory: Any | None = None,
) -> T:
    """Call LLM requiring structured JSON output matching Pydantic model T.

    Performs one automatic repair attempt if output is invalid.
    """
    raw_response = await call_llm_text(provider, prompt=prompt, model=model)
    json_text = _extract_json_substring(raw_response)

    try:
        return model_cls.model_validate_json(json_text)
    except (ValidationError, json.JSONDecodeError) as first_err:
        logger.warning(
            f"Failed to parse {model_cls.__name__} JSON on first attempt: {first_err}. Attempting repair."
        )

        repair_prompt = get_prompt(
            "schema_retry",
            error=str(first_err),
            previous_response=raw_response,
            schema_prompt=prompt,
        )

        repaired_raw = await call_llm_text(provider, prompt=repair_prompt, model=model)
        repaired_json = _extract_json_substring(repaired_raw)
        try:
            return model_cls.model_validate_json(repaired_json)
        except Exception as second_err:
            logger.error(
                f"Failed to parse {model_cls.__name__} JSON after repair attempt: {second_err}."
            )
            if fallback_factory is not None:
                return fallback_factory()
            raise JSONParsingError(
                f"Model failed to produce valid {model_cls.__name__} JSON: {second_err}",
                raw_output=repaired_raw,
            ) from second_err
