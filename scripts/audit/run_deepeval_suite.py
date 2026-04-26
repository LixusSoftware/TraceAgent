from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select

from _common import REPORTS_ROOT, utc_now_iso, write_json, write_text
from visor_agentico.config import get_settings
from visor_agentico.db import create_session_factory
from visor_agentico.models import Run


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate answer relevancy from completed runs.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum number of runs to evaluate.")
    parser.add_argument(
        "--mode",
        choices=["auto", "deepeval", "heuristic"],
        default="auto",
        help="Scoring mode.",
    )
    parser.add_argument("--threshold", type=float, default=0.2, help="Minimum passing score.")
    parser.add_argument("--database-url", default=None, help="Override database URL.")
    return parser.parse_args()


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value) if len(token) > 2}


def _heuristic_score(goal: str, output: str) -> float:
    goal_tokens = _tokens(goal)
    output_tokens = _tokens(output)
    if not goal_tokens:
        return 0.0
    overlap = len(goal_tokens & output_tokens)
    return overlap / len(goal_tokens)


def _load_runs(database_url: str, limit: int) -> list[Run]:
    _, session_factory = create_session_factory(database_url)
    with session_factory() as session:
        runs = list(
            session.scalars(
                select(Run)
                .where(Run.status == "completed")
                .where(Run.final_output_summary.isnot(None))
                .order_by(Run.started_at.desc())
                .limit(limit)
            )
        )
    return runs


def _evaluate_with_deepeval(runs: list[Run], threshold: float) -> tuple[list[dict[str, Any]], str]:
    try:
        from deepeval.metrics import AnswerRelevancyMetric  # type: ignore
        from deepeval.test_case import LLMTestCase  # type: ignore
    except Exception as exc:
        return [], f"deepeval import failed: {exc}"

    metric = AnswerRelevancyMetric(threshold=threshold, include_reason=True)
    rows: list[dict[str, Any]] = []
    for run in runs:
        goal = run.goal or ""
        output = run.final_output_summary or ""
        try:
            test_case = LLMTestCase(input=goal, actual_output=output)
            metric.measure(test_case)
            score = float(metric.score or 0.0)
            reason = str(metric.reason or "")
            passed = bool(metric.is_successful())
        except Exception as exc:
            score = _heuristic_score(goal, output)
            reason = f"deepeval_failed:{exc}"
            passed = score >= threshold

        rows.append(
            {
                "run_id": run.id,
                "goal": goal,
                "score": round(score, 4),
                "passed": passed,
                "reason": reason,
                "mode": "deepeval",
            }
        )

    return rows, "ok"


def _evaluate_with_heuristic(runs: list[Run], threshold: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        score = _heuristic_score(run.goal or "", run.final_output_summary or "")
        rows.append(
            {
                "run_id": run.id,
                "goal": run.goal,
                "score": round(score, 4),
                "passed": score >= threshold,
                "reason": "token_overlap",
                "mode": "heuristic",
            }
        )
    return rows


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# DeepEval Report",
        "",
        f"Generated at: {payload['created_at']}",
        f"Mode: {payload['mode_used']}",
        f"Evaluated runs: {payload['evaluated_count']}",
        f"Pass rate: {payload['pass_rate']}",
        "",
        "| Run ID | Score | Passed | Reason |",
        "|---|---:|---|---|",
    ]

    for item in payload["results"]:
        lines.append(f"| {item['run_id']} | {item['score']} | {item['passed']} | {item['reason']} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = args.database_url or settings.database_url
    report_dir = REPORTS_ROOT / "deepeval"
    report_dir.mkdir(parents=True, exist_ok=True)

    runs = _load_runs(database_url, args.limit)
    if not runs:
        payload = {
            "created_at": utc_now_iso(),
            "status": "no_data",
            "message": "No completed runs with final output found.",
            "results": [],
        }
        write_json(report_dir / "summary.json", payload)
        write_text(report_dir / "report.md", "# DeepEval Report\n\nNo completed runs with final output found.\n")
        print("No runs available for evaluation.")
        return 0

    mode_used = args.mode
    deepeval_status = "not_requested"
    if args.mode in {"auto", "deepeval"}:
        deepeval_rows, deepeval_status = _evaluate_with_deepeval(runs, args.threshold)
        if deepeval_rows:
            results = deepeval_rows
            mode_used = "deepeval"
        elif args.mode == "deepeval":
            results = _evaluate_with_heuristic(runs, args.threshold)
            mode_used = "heuristic"
        else:
            results = _evaluate_with_heuristic(runs, args.threshold)
            mode_used = "heuristic"
    else:
        results = _evaluate_with_heuristic(runs, args.threshold)

    pass_count = sum(1 for row in results if row["passed"])
    payload = {
        "created_at": utc_now_iso(),
        "status": "ok",
        "mode_requested": args.mode,
        "mode_used": mode_used,
        "deepeval_status": deepeval_status,
        "threshold": args.threshold,
        "evaluated_count": len(results),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / max(1, len(results)), 4),
        "results": results,
    }
    write_json(report_dir / "summary.json", payload)
    write_text(report_dir / "report.md", _render_markdown(payload))

    print("DeepEval report written to", report_dir / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
