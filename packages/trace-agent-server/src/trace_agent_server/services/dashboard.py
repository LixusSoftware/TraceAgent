from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trace_agent_server.models import Event, Run
from trace_agent_server.schemas import (
    DashboardResponse,
    DashboardStats,
    DashboardTrendItem,
    DashboardTopTool,
    DashboardTopError,
)


def build_dashboard(session: Session, period: str) -> DashboardResponse:
    now = datetime.now(timezone.utc)
    if period == "24h":
        cutoff = now - timedelta(hours=24)
    elif period == "7d":
        cutoff = now - timedelta(days=7)
    else:  # 30d
        cutoff = now - timedelta(days=30)

    # Base query for runs in period
    base_query = select(Run).where(Run.started_at >= cutoff)
    runs = list(session.scalars(base_query))

    total = len(runs)
    completed = sum(1 for r in runs if r.status == "completed")
    failed = sum(1 for r in runs if r.status == "failed")
    running = sum(1 for r in runs if r.status == "running")
    total_errors = sum(r.error_count for r in runs)
    total_tools = sum(r.tool_count for r in runs)
    total_artifacts = sum(r.artifact_count for r in runs)
    total_prompt = sum(r.total_prompt_tokens for r in runs)
    total_completion = sum(r.total_completion_tokens for r in runs)

    durations = [
        int((r.ended_at - r.started_at).total_seconds() * 1000)
        for r in runs
        if r.ended_at and r.started_at
    ]
    avg_duration = int(sum(durations) / len(durations)) if durations else None

    # Trend: daily counts for last 7 days
    trend = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_runs = list(session.scalars(
            select(Run).where(Run.started_at >= day_start, Run.started_at < day_end)
        ))
        trend.append(DashboardTrendItem(
            date=day_start.strftime("%Y-%m-%d"),
            runs=len(day_runs),
            completed=sum(1 for r in day_runs if r.status == "completed"),
            failed=sum(1 for r in day_runs if r.status == "failed"),
        ))

    # Top tools from events
    tool_stats = session.execute(
        select(Event.tool_name, func.count(Event.id), func.avg(Event.duration_ms))
        .where(Event.type.in_(["tool.succeeded", "tool.failed"]), Event.timestamp >= cutoff)
        .group_by(Event.tool_name)
        .order_by(func.count(Event.id).desc())
        .limit(10)
    ).all()
    top_tools = [
        DashboardTopTool(tool_name=name or "unknown", call_count=count, avg_duration_ms=int(avg_ms or 0))
        for name, count, avg_ms in tool_stats
    ]

    # Top errors
    error_stats = session.execute(
        select(Event.error_code, func.count(Event.id))
        .where(Event.error_code.isnot(None), Event.timestamp >= cutoff)
        .group_by(Event.error_code)
        .order_by(func.count(Event.id).desc())
        .limit(10)
    ).all()
    top_errors = [
        DashboardTopError(error_code=code, count=count)
        for code, count in error_stats
    ]

    # Provider distribution
    provider_dist = session.execute(
        select(Run.provider, func.count(Run.id))
        .where(Run.started_at >= cutoff)
        .group_by(Run.provider)
    ).all()
    provider_distribution = [{"provider": p or "unknown", "count": c} for p, c in provider_dist]

    # Model distribution
    model_dist = session.execute(
        select(Run.model, func.count(Run.id))
        .where(Run.started_at >= cutoff)
        .group_by(Run.model)
    ).all()
    model_distribution = [{"model": m, "count": c} for m, c in model_dist if m]

    return DashboardResponse(
        stats=DashboardStats(
            total_runs=total,
            completed_runs=completed,
            failed_runs=failed,
            running_runs=running,
            total_errors=total_errors,
            total_tools=total_tools,
            total_artifacts=total_artifacts,
            avg_duration_ms=avg_duration,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_prompt + total_completion,
        ),
        trend=trend,
        top_tools=top_tools,
        top_errors=top_errors,
        provider_distribution=provider_distribution,
        model_distribution=model_distribution,
    )
