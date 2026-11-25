"""Pure grounding verification functions and deterministic fallback synthesizer."""

import re
from typing import Any

from medicare.config_loader import get_app_config, get_verifier_terms, msg
from medicare.medicare.graph.routing import is_underspecified_comparison
from medicare.medicare.graph.state import (
    Citation,
    GroundingReport,
    PolicyAgentResult,
    SQLAgentResult,
    SupervisorPlan,
    TableResult,
    format_inr,
)


def _load_policy_vocabulary() -> list[str]:
    """Load policy vocabulary indicators from config."""
    terms = get_verifier_terms()
    return terms.get("policy_vocabulary", [])


POLICY_VOCABULARY = _load_policy_vocabulary()


def _normalize_num_string(val_str: str) -> float | None:
    """Normalize numeric expressions including lakhs, commas, rupee symbols."""
    sym = get_app_config().get("currency_symbol", "")
    clean = val_str.lower().replace(",", "")
    if sym:
        clean = clean.replace(sym.lower(), "")
    clean = clean.replace("rs.", "").replace("rs", "").strip()
    # Check lakh e.g. "1.5 lakh" or "2.5lakh"
    lakh_match = re.match(r"^([\d.]+)\s*(?:lakh|lac)s?$", clean)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000.0
        except ValueError:
            return None

    try:
        return float(clean)
    except ValueError:
        return None


def _extract_evidence_numbers(table: TableResult | None, citations: list[Citation]) -> set[float]:
    """Collect all normalized numeric values present in table and cited texts."""
    nums: set[float] = set()

    if table and table.rows:
        for row in table.rows:
            for cell in row:
                if isinstance(cell, (int, float)):
                    nums.add(float(cell))
                elif isinstance(cell, str):
                    # Find all numbers in string
                    matches = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", cell)
                    for m in matches:
                        n = _normalize_num_string(m)
                        if n is not None:
                            nums.add(n)

    sym = get_app_config().get("currency_symbol", "")
    prefix_pat = rf"(?:{re.escape(sym)}|rs\.?\s*)" if sym else r"(?:rs\.?\s*)"

    for c in citations:
        matches = re.findall(
            rf"{prefix_pat}?\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:lakh|lac)?\b", c.text, re.IGNORECASE
        )
        for m in matches:
            n = _normalize_num_string(m)
            if n is not None:
                nums.add(n)

        # Also extract plain numbers and durations e.g. "2 years", "30 days"
        durations = re.findall(
            r"\b\d+(?:\.\d+)?\s*(?:day|month|year|hour|minute|%)s?\b", c.text, re.IGNORECASE
        )
        for d in durations:
            digits = re.findall(r"\d+(?:\.\d+)?", d)
            if digits:
                nums.add(float(digits[0]))

        # Plain numbers in citation text
        plain_nums = re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", c.text)
        for p in plain_nums:
            n = _normalize_num_string(p)
            if n is not None:
                nums.add(n)

    return nums


def _extract_answer_numeric_facts(text: str) -> list[tuple[str, float]]:
    """Extract numeric claims, rupee amounts, and durations from answer text."""
    facts: list[tuple[str, float]] = []

    sym = get_app_config().get("currency_symbol", "")
    prefix_pat = rf"(?:{re.escape(sym)}|rs\.?\s*)" if sym else r"(?:rs\.?\s*)"

    # 1. Rupee amounts with symbol, or with lakh/rupees suffix
    rupee_patterns = [
        rf"{prefix_pat}(\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:lakh|lac)s?)?)",
        r"\b(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:lakh|lac)s?\b",
        r"\b(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rupees|inr)\b",
    ]
    for pattern in rupee_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            raw = m.group(0).strip()
            num_str = m.group(1).strip()
            val = _normalize_num_string(num_str)
            if val is not None and val > 0:
                facts.append((raw, val))

    # 2. Time periods and percentages
    units_matches = re.finditer(
        r"\b(\d+(?:\.\d+)?)\s*(days?|months?|years?|hours?|minutes?|%)\b", text, re.IGNORECASE
    )
    for m in units_matches:
        raw = m.group(0).strip()
        val = float(m.group(1))
        facts.append((raw, val))

    return facts


def verify_grounding(
    answer: str,
    table: TableResult | None,
    citations: list[Citation],
    known_hospitals: list[str] | None = None,
) -> GroundingReport:
    """Verify that claims, numbers, citations, and entities are grounded in evidence."""
    issues: list[str] = []

    if not answer.strip():
        return GroundingReport(passed=False, issues=["Answer is empty"])

    # 1. Verify Citation Markers [C1], [C2], etc.
    cited_markers = re.findall(r"\[(C\d+)\]", answer)
    available_cite_ids = {c.cite_id for c in citations if c.cite_id}
    # Also support 1-based indexing C1, C2 from citation list length
    indexed_cite_ids = {f"C{idx}" for idx in range(1, len(citations) + 1)}
    valid_cite_ids = available_cite_ids | indexed_cite_ids

    for marker in cited_markers:
        if marker not in valid_cite_ids:
            issues.append(msg("issue_citation_marker", marker=marker))

    # 2. Verify Policy Claims are Grounded
    paragraphs = answer.split("\n\n")
    for para in paragraphs:
        # Skip markdown tables and section headings
        trimmed = para.strip()
        if trimmed.startswith("|") or " | " in trimmed or trimmed.startswith("#"):
            continue

        para_has_citation = bool(re.search(r"\[C\d+\]", para))
        sentences = re.split(r"(?<=[.!?])\s+", para)
        for s in sentences:
            s_lower = s.lower()
            has_policy_kw = any(kw in s_lower for kw in POLICY_VOCABULARY)
            if has_policy_kw:
                # If documents exist, sentence or paragraph must carry citation marker [Cn]
                if citations:
                    has_citation = para_has_citation or bool(re.search(r"\[C\d+\]", s))
                    if (
                        not has_citation
                        and "not covered" not in s_lower
                        and "no policy" not in s_lower
                        and any(c.isdigit() for c in s)
                    ):
                        issues.append(msg("issue_policy_claim_uncited", sentence=s[:60]))
                else:
                    # No policy citations exist; statement must say documents do not cover or no evidence
                    disclaimer_words = get_verifier_terms().get("disclaimer_words", [])
                    if not any(dw in s_lower for dw in disclaimer_words) and any(
                        c.isdigit() for c in s
                    ):
                        issues.append(msg("issue_policy_claim_no_evidence", sentence=s[:60]))

    # 3. Verify Numeric Facts
    evidence_nums = _extract_evidence_numbers(table, citations)
    answer_facts = _extract_answer_numeric_facts(answer)

    # Allow common small constants, days/months, or UI section headings
    exempt_numbers = set(get_verifier_terms().get("exempt_numbers", []))

    for raw_expr, val in answer_facts:
        if val in exempt_numbers:
            continue
        # Check if value matches any evidence number within 1% tolerance
        matched = any(abs(val - ev) <= max(1.0, ev * 0.01) for ev in evidence_nums)
        if not matched:
            issues.append(msg("issue_numeric_claim_unmatched", raw_expr=raw_expr, val=val))

    # 4. Verify Hospital Entity Mentions (if table exists)
    if table and table.rows and known_hospitals:
        # Check mentioned hospital names against table
        table_hospitals = set()
        for row in table.rows:
            if row:
                table_hospitals.add(str(row[0]).lower())

        for hosp in known_hospitals:
            if hosp.lower() in answer.lower() and not any(
                hosp.lower() in th for th in table_hospitals
            ):
                issues.append(msg("issue_entity_unmatched", hosp=hosp))

    passed = len(issues) == 0
    return GroundingReport(passed=passed, issues=issues)


def build_scoping_response(
    entities: dict[str, Any],
    hospitals: list[str],
    min_cost: int | float | None,
    max_cost: int | float | None,
    disclaimers: list[str] | None = None,
) -> str:
    """Build grounded progressive scoping message with candidate hospitals and counter-questions."""
    count = len(hospitals)
    city = entities.get("city") or "the selected location"
    proc = entities.get("procedure") or "the requested procedure"
    min_p = format_inr(min_cost)
    max_p = format_inr(max_cost)
    hosp_list = "\n".join(f"• **{name}**" for name in hospitals[:3])

    heading = msg(
        "scoping_hospitals_heading",
        count=count,
        city=city,
        procedure=proc,
        min_price=min_p,
        max_price=max_p,
        hospital_list=hosp_list,
    )
    q1 = msg("scoping_q_insurance")
    q2 = msg("scoping_q_priority")
    quick = msg("scoping_quick_options_caption")

    all_disclaimers = list(disclaimers or [])
    all_disclaimers.append(msg("fallback_disclaimer"))
    disclaimer_str = "\n\n".join(all_disclaimers)

    return f"{heading}\n\n{q1}\n{q2}\n\n{quick}\n\n{disclaimer_str}"


def build_deterministic_fallback(
    plan: SupervisorPlan,
    sql_result: SQLAgentResult | None,
    policy_result: PolicyAgentResult | None,
    disclaimers: list[str] | None = None,
) -> str:
    """Construct a strictly grounded, structured fallback response in pure code."""
    # Check if broad underspecified comparison requiring progressive scoping
    if (
        sql_result
        and sql_result.table
        and sql_result.table.rows
        and is_underspecified_comparison(
            plan.rewritten_question, plan.entities, candidate_count=len(sql_result.table.rows)
        )
    ):
        tbl = sql_result.table
        hosp_names: list[str] = []
        costs: list[float] = []

        cost_idx = -1
        for idx, col in enumerate(tbl.columns):
            c_lower = col.lower()
            if any(term in c_lower for term in ("avg_cost", "package_cost", "cost", "tariff")):
                cost_idx = idx
                break

        for row in tbl.rows:
            if row:
                hosp_names.append(str(row[0]))
                if cost_idx >= 0 and cost_idx < len(row):
                    val = row[cost_idx]
                    if isinstance(val, (int, float)):
                        costs.append(float(val))

        min_c = min(costs) if costs else 0
        max_c = max(costs) if costs else 0

        return build_scoping_response(
            entities=plan.entities,
            hospitals=hosp_names,
            min_cost=min_c,
            max_cost=max_c,
            disclaimers=disclaimers,
        )

    # Check if hospital count inquiry
    q_lower = (plan.rewritten_question or "").lower()
    is_count_query = any(
        term in q_lower
        for term in (
            "how many hospital",
            "how much hospital",
            "count of hospital",
            "number of hospital",
        )
    )
    if is_count_query:
        city = plan.entities.get("city") or "the selected location"
        count = 0
        hosp_names: list[str] = []
        if sql_result and sql_result.table and sql_result.table.rows:
            tbl = sql_result.table
            if (
                len(tbl.rows) == 1
                and len(tbl.rows[0]) == 1
                and isinstance(tbl.rows[0][0], (int, float))
            ):
                count = int(tbl.rows[0][0])
            else:
                count = len(tbl.rows)
                for r in tbl.rows[:5]:
                    if r:
                        hosp_names.append(str(r[0]))

        disclaimer = msg("fallback_disclaimer")
        if count > 0:
            summary = msg("hospital_count_summary", count=count, city=city)
            list_md = ""
            if hosp_names:
                list_md = "\n\n" + "\n".join(f"• **{name}**" for name in hosp_names)
            next_steps = msg("hospital_count_next_steps")
            return f"{msg('fallback_heading_summary')}\n\n{summary}{list_md}\n\n### 2. Available Guidance\n\n{next_steps}\n\n{disclaimer}"
        else:
            no_rec = msg("hospital_count_no_records", city=city)
            return f"{msg('fallback_heading_summary')}\n\n{no_rec}\n\n{disclaimer}"

    sections: list[str] = []

    # 1. Summary
    proc = plan.entities.get("procedure") or "the requested procedure"
    city = plan.entities.get("city") or "the specified location"
    summary_text = msg("fallback_summary", procedure=proc, city=city)
    sections.append(f"{msg('fallback_heading_summary')}\n\n{summary_text}")

    # 2. Cost & Wait-Time Comparison Table
    if sql_result and sql_result.table and sql_result.table.rows:
        tbl = sql_result.table
        col_headers = [c.replace("_", " ").title() for c in tbl.columns]
        header_row = "| " + " | ".join(col_headers) + " |"
        sep_row = "| " + " | ".join(["---"] * len(col_headers)) + " |"
        rows_text = []
        for r in tbl.rows[:5]:
            formatted_cells = []
            for idx, c in enumerate(r):
                c_name = tbl.columns[idx].lower() if idx < len(tbl.columns) else ""
                if "cost" in c_name and isinstance(c, (int, float)):
                    formatted_cells.append(format_inr(c))
                else:
                    formatted_cells.append(str(c) if c is not None else "-")
            rows_text.append("| " + " | ".join(formatted_cells) + " |")

        table_md = "\n".join([header_row, sep_row] + rows_text)
        sections.append(f"{msg('fallback_heading_comparison')}\n\n{table_md}")
    elif sql_result and sql_result.empty_db:
        sections.append(
            f"{msg('fallback_heading_comparison')}\n\n{msg('fallback_no_hospital_records')}"
        )

    # 3. Insurance Policy Clauses & Citations
    if policy_result and policy_result.citations:
        notes: list[str] = []
        for idx, c in enumerate(policy_result.citations, start=1):
            cite_id = c.cite_id or f"C{idx}"
            notes.append(
                f"- **{c.section}** [{cite_id}]: {c.text.strip()}\n  *(Source: {c.source}"
                + (f", Page {c.page}" if c.page else "")
                + ")*"
            )
        sections.append(f"{msg('fallback_heading_policy')}\n\n" + "\n\n".join(notes))
    elif policy_result and (policy_result.no_evidence or policy_result.index_empty):
        sections.append(f"{msg('fallback_heading_policy')}\n\n{msg('fallback_no_policy_clauses')}")

    # 4. What To Do Next
    sections.append(f"{msg('fallback_heading_next_steps')}\n\n{msg('fallback_next_steps')}")

    # 5. Mandatory Medical Disclaimer
    all_disclaimers = list(disclaimers or [])
    all_disclaimers.append(msg("fallback_disclaimer"))
    sections.append("\n\n" + "\n\n".join(all_disclaimers))

    return "\n\n".join(sections)
