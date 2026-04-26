from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select

from _common import REPORTS_ROOT, utc_now_iso, write_json, write_text
from visor_agentico.config import get_settings
from visor_agentico.db import create_session_factory
from visor_agentico.models import Event, Run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate drift report using historical runs.")
    parser.add_argument("--reference-days", type=int, default=21, help="Days in the reference window.")
    parser.add_argument("--current-days", type=int, default=7, help="Days in the current window.")
    parser.add_argument("--database-url", default=None, help="Override database URL.")
    parser.add_argument("--use-evidently", action="store_true", help="Try to generate Evidently HTML report.")
    return parser.parse_args()


def _duration_ms(run: Run) -> int | None:
    if run.ended_at is None:
        return None
    return max(0, int((run.ended_at - run.started_at).total_seconds() * 1000))


def _token_usage(session, run_id: str) -> int:
    events = session.scalars(
        select(Event).where(Event.run_id == run_id).where(Event.type == "model.responded")
    )
    total = 0
    for event in events:
        usage = event.event_metadata.get("usage", {})
        if isinstance(usage, dict):
            total += int(usage.get("total_tokens") or 0)
    return total


def _load_frame(database_url: str) -> pd.DataFrame:
    _, session_factory = create_session_factory(database_url)
    rows: list[dict[str, Any]] = []

    with session_factory() as session:
        runs = list(session.scalars(select(Run).order_by(Run.started_at.desc())))
        for run in runs:
            rows.append(
                {
                    "run_id": run.id,
                    "started_at": run.started_at,
                    "status": run.status,
                    "tool_count": run.tool_count,
                    "error_count": run.error_count,
                    "retry_count": run.retry_count,
                    "duration_ms": _duration_ms(run),
                    "total_tokens": _token_usage(session, run.id),
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "run_id",
                "started_at",
                "status",
                "tool_count",
                "error_count",
                "retry_count",
                "duration_ms",
                "total_tokens",
            ]
        )

    frame = pd.DataFrame(rows)
    frame["started_at"] = pd.to_datetime(frame["started_at"], utc=True)
    frame["duration_ms"] = frame["duration_ms"].fillna(0)
    return frame


def _compute_summary(reference: pd.DataFrame, current: pd.DataFrame) -> list[dict[str, Any]]:
    metrics = ["tool_count", "error_count", "retry_count", "duration_ms", "total_tokens"]
    summary: list[dict[str, Any]] = []

    for metric in metrics:
        ref_mean = float(reference[metric].mean()) if not reference.empty else 0.0
        cur_mean = float(current[metric].mean()) if not current.empty else 0.0
        if ref_mean == 0:
            pct_change = 0.0 if cur_mean == 0 else 1.0
        else:
            pct_change = (cur_mean - ref_mean) / abs(ref_mean)

        summary.append(
            {
                "metric": metric,
                "reference_mean": round(ref_mean, 4),
                "current_mean": round(cur_mean, 4),
                "pct_change": round(pct_change, 4),
                "drift_flag": abs(pct_change) >= 0.25,
            }
        )

    return summary


def _try_evidently(reference: pd.DataFrame, current: pd.DataFrame, report_path: Path) -> dict[str, Any]:
    try:
        try:
            from evidently import Report
            from evidently.presets import DataDriftPreset
        except Exception:
            from evidently.report import Report
            from evidently.metric_preset import DataDriftPreset

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference, current_data=current)
        report.save_html(str(report_path))
        return {"enabled": True, "path": str(report_path)}
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def _markdown_report(
    *,
    generated_at: str,
    reference_count: int,
    current_count: int,
    summary_rows: list[dict[str, Any]],
    evidently_result: dict[str, Any] | None,
) -> str:
    lines = [
        "# Drift Report",
        "",
        f"Generated at: {generated_at}",
        "",
        f"Reference runs: {reference_count}",
        f"Current runs: {current_count}",
        "",
        "| Metric | Reference Mean | Current Mean | % Change | Drift Flag |",
        "|---|---:|---:|---:|---|",
    ]

    for row in summary_rows:
        lines.append(
            f"| {row['metric']} | {row['reference_mean']} | {row['current_mean']} | {row['pct_change']} | {row['drift_flag']} |"
        )

    if evidently_result is not None:
        lines.extend(
            [
                "",
                "## Evidently",
                "",
                f"{evidently_result}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    settings = get_settings()
    database_url = args.database_url or settings.database_url
    report_dir = REPORTS_ROOT / "drift"
    report_dir.mkdir(parents=True, exist_ok=True)

    frame = _load_frame(database_url)
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=args.current_days)
    reference_start = current_start - timedelta(days=args.reference_days)

    if frame.empty:
        payload = {
            "created_at": utc_now_iso(),
            "status": "no_data",
            "message": "No runs available.",
        }
        write_json(report_dir / "summary.json", payload)
        write_text(report_dir / "report.md", "# Drift Report\n\nNo runs available.\n")
        print("No runs available for drift report.")
        return 0

    reference = frame[(frame["started_at"] >= reference_start) & (frame["started_at"] < current_start)].copy()
    current = frame[frame["started_at"] >= current_start].copy()
    if reference.empty or current.empty:
        payload = {
            "created_at": utc_now_iso(),
            "status": "insufficient_data",
            "reference_count": int(len(reference)),
            "current_count": int(len(current)),
            "message": "Insufficient data in one of the windows.",
        }
        write_json(report_dir / "summary.json", payload)
        write_text(report_dir / "report.md", "# Drift Report\n\nInsufficient data in one of the windows.\n")
        print("Insufficient data in one of the windows.")
        return 0

    summary_rows = _compute_summary(reference, current)
    evidently_result = None
    if args.use_evidently:
        evidently_result = _try_evidently(reference, current, report_dir / "evidently.html")

    payload = {
        "created_at": utc_now_iso(),
        "status": "ok",
        "reference_count": int(len(reference)),
        "current_count": int(len(current)),
        "summary": summary_rows,
        "evidently": evidently_result,
    }
    write_json(report_dir / "summary.json", payload)
    write_text(
        report_dir / "report.md",
        _markdown_report(
            generated_at=payload["created_at"],
            reference_count=payload["reference_count"],
            current_count=payload["current_count"],
            summary_rows=summary_rows,
            evidently_result=evidently_result,
        ),
    )

    print("Drift report written to", report_dir / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
