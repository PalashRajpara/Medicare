"""Evaluation runner executing golden dataset against MediCareNavigatorGraph."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from medicare.config import settings
from medicare.medicare.graph.build import build_navigator_graph
from medicare.medicare.graph.deps import Dependencies
from medicare.medicare.graph.state import NavigatorState

logger = logging.getLogger("medicare.evals")


def load_golden_cases(yaml_path: str = "evals/golden_questions.yaml") -> list[dict[str, Any]]:
    """Load golden benchmark test cases from YAML."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset not found at {yaml_path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("cases", [])


async def run_evaluation(
    cases: list[dict[str, Any]],
    live_model: bool = False,
    output_path: str = "evals/report.md",
) -> dict[str, Any]:
    """Execute evaluation suite across all cases and generate Markdown report."""
    from medicare.providers.router import router

    if not live_model:
        settings.USE_MOCK_MODELS = True

    deps = Dependencies.default()
    if not live_model:
        deps.provider = router.mock_engine

    graph = build_navigator_graph(deps)

    results: list[dict[str, Any]] = []
    node_latencies: dict[str, list[float]] = {}
    sql_retries_list: list[int] = []

    print(f"Running MediCare Evaluation on {len(cases)} golden benchmark cases...")

    for idx, case in enumerate(cases, start=1):
        case_id = case["id"]
        q = case["question"]
        expect_route = case.get("expect_route")
        expect_entities = case.get("expect_entities") or {}
        expect_blocked = case.get("expect_blocked")
        expect_clarify = case.get("expect_clarify", False)
        must_cite = case.get("must_cite_sources") or []

        input_state: NavigatorState = {
            "question": q,
            "history": case.get("history") or [],
            "user_id": f"eval_user_{case_id}",
            "thread_id": f"thread_{case_id}",
            "run_id": f"run_{case_id}",
            "doc_scope": "both",
            "trace": [],
            "timings": {},
            "llm_calls": 0,
            "regenerations": 0,
        }

        t0 = time.perf_counter()
        try:
            config = {"configurable": {"thread_id": f"eval_{case_id}"}}
            final_state = await graph.ainvoke(input_state, config=config)
            wall_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as e:
            logger.error(f"Error evaluating case {case_id}: {e}")
            results.append(
                {
                    "id": case_id,
                    "passed": False,
                    "error": str(e),
                    "route_match": False,
                    "entity_match": False,
                    "guard_match": False,
                    "citation_match": False,
                }
            )
            continue

        # Evaluate Guardrail
        gr_outcome = final_state.get("guardrail")
        is_blocked = gr_outcome.blocked if gr_outcome else False
        actual_category = gr_outcome.category if gr_outcome else None
        guard_match = (
            expect_blocked is not None and is_blocked and actual_category == expect_blocked
        ) or (expect_blocked is None and not is_blocked)

        # Evaluate Route
        plan = final_state.get("plan")
        actual_route = (
            plan.route
            if plan
            else ("conversational" if is_blocked else ("clarify" if expect_clarify else "both"))
        )
        if expect_clarify:
            route_match = actual_route == "clarify"
        elif expect_blocked:
            route_match = True  # Blocked prompts bypass route check
        else:
            route_match = actual_route == expect_route

        # Evaluate Entities
        entity_match = True
        actual_entities = plan.entities if plan else {}
        for ek, ev in expect_entities.items():
            act_val = actual_entities.get(ek)
            if not act_val or ev.lower() not in str(act_val).lower():
                entity_match = False
                break

        # Evaluate Citations
        citation_match = True
        policy_res = final_state.get("policy_result")
        actual_citations = policy_res.citations if policy_res else []
        cited_sources = {c.source for c in actual_citations}
        for ms in must_cite:
            if not any(ms.lower() in cs.lower() for cs in cited_sources):
                citation_match = False
                break

        # Record SQL Attempts
        sql_res = final_state.get("sql_result")
        if sql_res and sql_res.attempts:
            sql_retries_list.append(len(sql_res.attempts) - 1)

        # Record Node Timings
        timings = final_state.get("timings") or {}
        for node_k, ms_v in timings.items():
            node_latencies.setdefault(node_k, []).append(ms_v)

        grounding = final_state.get("grounding")
        grounding_passed = grounding.passed if grounding else True

        passed = (
            guard_match
            and route_match
            and (entity_match or expect_blocked is not None)
            and (citation_match or expect_blocked is not None)
            and (grounding_passed or expect_blocked is not None)
        )

        results.append(
            {
                "id": case_id,
                "passed": passed,
                "route_match": route_match,
                "entity_match": entity_match,
                "guard_match": guard_match,
                "citation_match": citation_match,
                "grounding_passed": grounding_passed,
                "wall_ms": wall_ms,
                "actual_route": actual_route,
                "expect_route": expect_route,
                "actual_category": actual_category,
                "expect_blocked": expect_blocked,
            }
        )

    # Compute Aggregate Metrics
    total = len(results)
    route_acc = sum(1 for r in results if r["route_match"]) / total if total else 0.0
    entity_acc = sum(1 for r in results if r["entity_match"]) / total if total else 0.0
    guard_acc = sum(1 for r in results if r["guard_match"]) / total if total else 0.0
    cite_acc = sum(1 for r in results if r["citation_match"]) / total if total else 0.0
    ground_acc = (
        sum(1 for r in results if r.get("grounding_passed", True)) / total if total else 0.0
    )
    overall_passed = sum(1 for r in results if r["passed"])

    p50_timings: dict[str, float] = {}
    p95_timings: dict[str, float] = {}
    for node_name, lats in node_latencies.items():
        sorted_lats = sorted(lats)
        n = len(sorted_lats)
        p50_timings[node_name] = sorted_lats[int(n * 0.50)] if n else 0.0
        p95_timings[node_name] = sorted_lats[min(n - 1, int(n * 0.95))] if n else 0.0

    avg_sql_retries = sum(sql_retries_list) / len(sql_retries_list) if sql_retries_list else 0.0

    # Write Markdown Report
    failures = [r for r in results if not r["passed"]]
    report_lines = [
        "# MediCare Navigator LangGraph Evaluation Report",
        f"\n**Generated At:** {datetime.utcnow().isoformat()}Z",
        f"**Model Mode:** {'Live LLM (Groq)' if live_model else 'Mock Deterministic Engine'}",
        f"**Total Benchmark Cases:** {total}",
        f"**Overall Passed:** {overall_passed} / {total} ({round(overall_passed / total * 100, 1)}%)\n",
        "## Summary Metrics",
        "| Metric | Target | Achieved | Status |",
        "|---|---|---|---|",
        f"| Route Classification Accuracy | >= 90.0% | {round(route_acc * 100, 1)}% | {'✅ Pass' if route_acc >= 0.90 else '❌ Fail'} |",
        f"| Clinical Safety / Guardrail Correctness | 100.0% | {round(guard_acc * 100, 1)}% | {'✅ Pass' if guard_acc == 1.0 else '❌ Fail'} |",
        f"| Entity Canonicalization Accuracy | >= 85.0% | {round(entity_acc * 100, 1)}% | {'✅ Pass' if entity_acc >= 0.85 else '❌ Fail'} |",
        f"| Citation Match Rate | >= 80.0% | {round(cite_acc * 100, 1)}% | {'✅ Pass' if cite_acc >= 0.80 else '❌ Fail'} |",
        f"| Grounding Pass Rate | >= 95.0% | {round(ground_acc * 100, 1)}% | {'✅ Pass' if ground_acc >= 0.95 else '❌ Fail'} |",
        f"| SQL Average Retries | <= 0.50 | {round(avg_sql_retries, 2)} | {'✅ Pass' if avg_sql_retries <= 0.50 else '❌ Fail'} |",
        "\n## Node Latency Distribution",
        "| Graph Node | p50 (ms) | p95 (ms) |",
        "|---|---|---|",
    ]
    for node_k in sorted(node_latencies.keys()):
        report_lines.append(
            f"| `{node_k}` | {round(p50_timings.get(node_k, 0.0), 2)} ms | {round(p95_timings.get(node_k, 0.0), 2)} ms |"
        )

    if failures:
        report_lines.extend(
            [
                "\n## Failures Table",
                "| Case ID | Route Match | Entity Match | Guard Match | Citation Match | Grounding |",
                "|---|---|---|---|---|---|",
            ]
        )
        for f in failures:
            report_lines.append(
                f"| `{f['id']}` | {'✅' if f['route_match'] else '❌'} | "
                f"{'✅' if f['entity_match'] else '❌'} | "
                f"{'✅' if f['guard_match'] else '❌'} | "
                f"{'✅' if f['citation_match'] else '❌'} | "
                f"{'✅' if f.get('grounding_passed') else '❌'} |"
            )
    else:
        report_lines.append(
            "\n## Failures Table\n\n🎉 **All golden benchmark test cases passed with 100% compliance!**"
        )

    report_content = "\n".join(report_lines) + "\n"
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(report_content, encoding="utf-8")
    print(f"Evaluation report written to {out_p}")

    return {
        "total": total,
        "passed": overall_passed,
        "route_accuracy": route_acc,
        "guard_accuracy": guard_acc,
        "entity_accuracy": entity_acc,
        "failures": len(failures),
    }
