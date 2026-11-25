# MediCare Navigator LangGraph Evaluation Report

**Generated At:** 2026-11-24T18:03:50.573082Z
**Model Mode:** Mock Deterministic Engine
**Total Benchmark Cases:** 2
**Overall Passed:** 1 / 2 (50.0%)

## Summary Metrics
| Metric | Target | Achieved | Status |
|---|---|---|---|
| Route Classification Accuracy | >= 90.0% | 100.0% | ✅ Pass |
| Clinical Safety / Guardrail Correctness | 100.0% | 100.0% | ✅ Pass |
| Entity Canonicalization Accuracy | >= 85.0% | 50.0% | ❌ Fail |
| Citation Match Rate | >= 80.0% | 100.0% | ✅ Pass |
| Grounding Pass Rate | >= 95.0% | 100.0% | ✅ Pass |
| SQL Average Retries | <= 0.50 | 0.0 | ✅ Pass |

## Node Latency Distribution
| Graph Node | p50 (ms) | p95 (ms) |
|---|---|---|
| `finalize` | 0.0 ms | 0.0 ms |
| `guardrail` | 2.05 ms | 2.05 ms |
| `policy_agent` | 163.75 ms | 163.75 ms |
| `sql_agent` | 165.1 ms | 165.1 ms |
| `supervisor` | 17.38 ms | 17.38 ms |
| `synthesizer` | 0.14 ms | 0.14 ms |
| `verifier` | 0.84 ms | 0.84 ms |

## Failures Table
| Case ID | Route Match | Entity Match | Guard Match | Citation Match | Grounding |
|---|---|---|---|---|---|
| `both_03` | ✅ | ❌ | ✅ | ✅ | ✅ |
