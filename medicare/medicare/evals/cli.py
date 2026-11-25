"""CLI entry point for MediCare Navigator evaluation runner."""

import argparse
import asyncio
import sys

from medicare.medicare.evals.runner import load_golden_cases, run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="MediCare Navigator Golden Evals Runner")
    parser.add_argument("--live", action="store_true", help="Run against live Groq model")
    parser.add_argument("--out", default="evals/report.md", help="Output path for markdown report")
    parser.add_argument(
        "--dataset", default="evals/golden_questions.yaml", help="YAML dataset path"
    )
    args = parser.parse_args()

    cases = load_golden_cases(args.dataset)
    metrics = asyncio.run(run_evaluation(cases, live_model=args.live, output_path=args.out))

    # Exit non-zero if route accuracy < 90% or any guardrail failure
    if metrics["route_accuracy"] < 0.90 or metrics["guard_accuracy"] < 1.0:
        print("Evaluation FAILED target thresholds!")
        sys.exit(1)
    else:
        print(f"Evaluation SUCCESS! Route accuracy: {round(metrics['route_accuracy'] * 100, 1)}%")


if __name__ == "__main__":
    main()
