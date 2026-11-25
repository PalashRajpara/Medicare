"""Pure routing functions and dynamic entity canonicalization for LangGraph conditional edges."""

import difflib
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from medicare.config import settings
from medicare.config_loader import msg
from medicare.medicare.graph.state import NavigatorState, SupervisorPlan
from medicare.tools.db_tools import get_known_catalog as _get_known_catalog

logger = logging.getLogger(__name__)


def _load_intent_config() -> dict[str, Any]:
    """Load intent vocabulary and keyword indicators from YAML."""
    config_dir = getattr(settings, "CONFIG_DIR", "config")
    p = Path(config_dir) / "intent_words.yaml"
    if not p.exists():
        p = Path(__file__).resolve().parent.parent.parent.parent / "config" / "intent_words.yaml"
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning("Failed to load intent_words.yaml (%s)", e)
    return {}


_INTENT_CONFIG = _load_intent_config()

CONVERSATIONAL_GREETINGS: set[str] = set(
    _INTENT_CONFIG.get(
        "conversational_greetings",
        [
            "hello",
            "hi",
            "hey",
            "good morning",
            "good afternoon",
            "good evening",
            "help",
            "thanks",
            "thank you",
        ],
    )
)

CONVERSATIONAL_PATTERNS: list[str] = _INTENT_CONFIG.get(
    "conversational_patterns",
    [
        r"^(hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b",
        r"\bwho\s+are\s+you\b",
        r"\bhow\s+can\s+you\s+help\b",
        r"\bcan\s+you\s+assist\b",
        r"\bwhat\s+can\s+you\s+do\b",
        r"\bthanks\s+for\s+your\s+help\b",
        r"\bhave\s+a\s+great\s+day\b",
    ],
)

POLICY_INDICATORS: list[str] = _INTENT_CONFIG.get("policy_indicators", [])

DATA_INDICATORS: list[str] = _INTENT_CONFIG.get("data_indicators", [])

CLARIFY_INDICATORS: list[str] = _INTENT_CONFIG.get(
    "clarify_indicators",
    ["compare", "which hospital", "better", "cheapest", "best"],
)

COMPARATIVE_TERMS: list[str] = [
    "compare",
    "comparison",
    "which hospital",
    "best hospital",
    "hospitals in",
    "hospital in",
    "options in",
    "cost of",
    "costs of",
    "where to get",
    "treatment in",
    "surgery in",
]

SPECIFIC_CRITERIA_TERMS: list[str] = [
    "cheapest",
    "cheap",
    "lowest",
    "min cost",
    "minimum cost",
    "highest",
    "max cost",
    "maximum cost",
    "fastest",
    "quickest",
    "shortest wait",
    "least wait",
    "cash price",
    "cash-price",
    "insurance price",
    "bed charge",
    "icu",
    "room rent",
    "doctor fee",
    "consultation",
]

FULL_TABLE_TERMS: list[str] = [
    "full table",
    "table",
    "complete list",
    "all hospitals",
    "show all",
    "breakdown",
    "matrix",
    "everything",
]


def is_underspecified_comparison(
    question: str,
    entities: dict[str, Any],
    candidate_count: int = 2,
) -> bool:
    """Determine whether a query is a broad comparison lacking insurance, criteria, or full-table intent."""
    q_lower = question.lower()

    if entities.get("insurer"):
        return False

    if any(term in q_lower for term in SPECIFIC_CRITERIA_TERMS):
        return False

    if any(term in q_lower for term in FULL_TABLE_TERMS):
        return False

    has_target = bool(entities.get("procedure") or entities.get("city"))
    if not has_target:
        return False

    is_comparative = any(term in q_lower for term in COMPARATIVE_TERMS)
    return is_comparative and candidate_count >= 2


def generate_scoping_followups(entities: dict[str, Any]) -> list[str]:
    """Generate interactive 1-click suggestion chips for scoping clarification."""
    city = entities.get("city") or "your city"
    return [
        msg("chip_lowest_cost", city=city),
        msg("chip_shortest_wait", city=city),
        msg("chip_check_insurance"),
        msg("chip_show_full_table"),
    ]


def canonicalize_entities(entities: dict[str, Any], db_path: str | None = None) -> dict[str, Any]:
    """Canonicalize extracted entity strings against live database values using difflib."""
    cities_map, procedures_map, insurers_map = _get_known_catalog(db_path)
    canon = dict(entities)

    # Match city
    raw_city = canon.get("city")
    if raw_city and isinstance(raw_city, str):
        c_lower = raw_city.strip().lower()
        if c_lower in cities_map:
            canon["city"] = cities_map[c_lower]
        elif cities_map:
            matches = difflib.get_close_matches(c_lower, list(cities_map.keys()), n=1, cutoff=0.75)
            if matches:
                canon["city"] = cities_map[matches[0]]
            else:
                canon["city_unmatched"] = True

    # Match procedure
    raw_proc = canon.get("procedure")
    if raw_proc and isinstance(raw_proc, str):
        p_lower = raw_proc.strip().lower()
        if p_lower in procedures_map:
            canon["procedure"] = procedures_map[p_lower]
        elif procedures_map:
            matches = difflib.get_close_matches(
                p_lower, list(procedures_map.keys()), n=1, cutoff=0.70
            )
            if matches:
                canon["procedure"] = procedures_map[matches[0]]
            else:
                canon["procedure_unmatched"] = True

    # Match insurer
    raw_ins = canon.get("insurer")
    if raw_ins and isinstance(raw_ins, str):
        i_lower = raw_ins.strip().lower()
        if i_lower in insurers_map:
            canon["insurer"] = insurers_map[i_lower]
        elif insurers_map:
            matches = difflib.get_close_matches(
                i_lower, list(insurers_map.keys()), n=1, cutoff=0.70
            )
            if matches:
                canon["insurer"] = insurers_map[matches[0]]
            else:
                canon["insurer_unmatched"] = True

    return canon


def rules_route(
    question: str, prior_prefs: dict[str, Any] | None = None, db_path: str | None = None
) -> SupervisorPlan:
    """Pure fallback intent classification using deterministic rules without static domain data."""
    q_lower = question.lower()
    cleaned_q = re.sub(r"[^\w\s]", "", q_lower).strip()

    # 1. Check for casual greetings (pure conversational)
    is_conversational_phrase = (cleaned_q in CONVERSATIONAL_GREETINGS) or any(
        re.search(p, q_lower) for p in CONVERSATIONAL_PATTERNS
    )

    has_policy = any(kw in q_lower for kw in POLICY_INDICATORS)
    has_data = any(kw in q_lower for kw in DATA_INDICATORS)

    if is_conversational_phrase and not has_policy and not has_data:
        return SupervisorPlan(
            route="conversational",
            entities={},
            rewritten_question=question,
            confidence=1.0,
            rationale=msg("routing_conversational_reason"),
        )

    # 2. Check for underspecified queries requiring clarification
    short_query = len(q_lower.split()) <= 4
    if (
        short_query
        and any(term in q_lower for term in CLARIFY_INDICATORS)
        and not has_policy
        and not has_data
    ):
        return SupervisorPlan(
            route="clarify",
            entities={},
            rewritten_question=question,
            confidence=0.95,
            needs_clarification=True,
            clarification_question=msg("clarification_default"),
            rationale=msg("routing_underspecified_reason"),
        )

    # 3. Dynamic entity extraction and canonicalization from live catalog
    cities_map, procedures_map, insurers_map = _get_known_catalog(db_path)
    entities: dict[str, Any] = dict(prior_prefs or {})

    # Extract city dynamically from question if not already in entities
    if "city" not in entities:
        for c_key in sorted(cities_map.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(c_key)}\b", q_lower):
                entities["city"] = cities_map[c_key]
                break
        if "city" not in entities:
            tokens = re.findall(r"\b[a-zA-Z]{4,}\b", q_lower)
            for token in tokens:
                matches = difflib.get_close_matches(
                    token, list(cities_map.keys()), n=1, cutoff=0.72
                )
                if matches:
                    entities["city"] = cities_map[matches[0]]
                    question = re.sub(
                        rf"\b{re.escape(token)}\b",
                        cities_map[matches[0]],
                        question,
                        flags=re.IGNORECASE,
                    )
                    break

    # Extract procedure dynamically from question if not already in entities
    if "procedure" not in entities:
        for p_key in sorted(procedures_map.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(p_key)}\b", q_lower):
                entities["procedure"] = procedures_map[p_key]
                break
        if "procedure" not in entities:
            words = re.findall(r"\b[a-zA-Z]+\b", q_lower)
            ngrams = []
            for n in (3, 2):
                for i in range(len(words) - n + 1):
                    ngrams.append(" ".join(words[i : i + n]))
            for ng in ngrams:
                matches = difflib.get_close_matches(
                    ng, list(procedures_map.keys()), n=1, cutoff=0.72
                )
                if matches:
                    entities["procedure"] = procedures_map[matches[0]]
                    question = re.sub(
                        rf"\b{re.escape(ng)}\b",
                        procedures_map[matches[0]],
                        question,
                        flags=re.IGNORECASE,
                    )
                    break

    # Extract insurer dynamically from question if not already in entities
    if "insurer" not in entities:
        for i_key in sorted(insurers_map.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(i_key)}\b", q_lower):
                entities["insurer"] = insurers_map[i_key]
                break

    entities = canonicalize_entities(entities, db_path=db_path)

    # 4. Determine Route
    if (
        "claim status" in q_lower
        or "claim was rejected" in q_lower
        or ("covered" in q_lower and "emergency room" in q_lower and not has_data)
    ):
        route = "policy_only"
    elif has_policy and has_data:
        route = "both"
    elif has_policy:
        route = "policy_only"
    elif has_data:
        route = "data_only"
    elif entities.get("procedure") or entities.get("city"):
        route = "both" if entities.get("insurer") else "data_only"
    elif entities.get("insurer"):
        route = "policy_only"
    else:
        route = "both"

    scoping_needed = is_underspecified_comparison(question, entities, candidate_count=2)

    return SupervisorPlan(
        route=route,
        entities=entities,
        rewritten_question=question,
        confidence=0.88,
        needs_clarification=scoping_needed,
        rationale=msg("routing_scoping_reason")
        if scoping_needed
        else f"Classified into '{route}' via deterministic rules.",
    )


def route_guardrail(state: NavigatorState) -> str:
    """Conditional edge evaluating guardrail outcome."""
    outcome = state.get("guardrail")
    if outcome and outcome.blocked:
        return "blocked_response"
    return "supervisor"


def route_supervisor(state: NavigatorState) -> list[str]:
    """Conditional edge fanning out from supervisor to workers in parallel."""
    plan = state.get("plan")
    route = plan.route if plan else "both"

    if route == "conversational":
        return ["conversational"]
    if route == "clarify":
        return ["clarify"]
    if route == "policy_only":
        return ["policy_agent"]
    if route == "data_only":
        return ["sql_agent"]
    # "both" -> fan out concurrently!
    return ["sql_agent", "policy_agent"]


def route_verifier(state: NavigatorState) -> str:
    """Conditional edge evaluating whether to loop back to synthesizer or finalize."""
    report = state.get("grounding")
    regenerations = state.get("regenerations", 0)
    max_regen = settings.VERIFIER_MAX_REGENERATIONS

    if report is None or report.passed or report.fallback_used:
        return "finalize"

    if regenerations < max_regen:
        return "synthesizer"

    return "finalize"
