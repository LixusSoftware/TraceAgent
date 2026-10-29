"""Run bookkeeping shared by every way a run can be fed: REST endpoints and the OTLP receiver."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from trace_agent_sdk.redaction import stable_hash, summarize_value
from trace_agent_server.models import Run
from trace_agent_server.schemas import ArtifactInput, ToolResultInput
from trace_agent_server.services.events import create_artifact, record_event, utcnow
from trace_agent_server.services.explanation import derive_explanation


def token_count(value: Any) -> int:
    """Return a usable token count from untrusted observation metadata."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 0


def apply_llm_usage(
    run: Run,
    *,
    provider: str | None,
    model: str | None,
    prompt_tokens: Any = None,
    completion_tokens: Any = None,
) -> None:
    """Fill the run's provider, model and token totals from a finished model call.

    Framework integrations report model usage per call instead of through /turns.
    The first provider and model win, and "unknown" providers are ignored.
    """
    if not run.provider and provider not in (None, "", "unknown"):
        run.provider = provider
    if not run.model and model:
        run.model = model
    run.total_prompt_tokens += token_count(prompt_tokens)
    run.total_completion_tokens += token_count(completion_tokens)


def record_tool_result(
    session: Session,
    run: Run,
    result: ToolResultInput,
    *,
    capture_full: bool,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> None:
    """Record a finished tool call: its started and completed events, counters and artifacts.

    ``started_at``/``ended_at`` carry the real times when the source reports them.
    """
    started_event = record_event(
        session,
        run,
        actor="sdk",
        event_type="tool.started",
        summary=f"Started {result.name}.",
        status="running",
        step_id=result.step_id,
        parent_step_id=result.parent_step_id,
        tool_name=result.name,
        payload_hash=stable_hash(result.args),
        payload_full={"args": result.args} if capture_full else None,
        metadata={"call_id": result.call_id, "args_summary": summarize_value(result.args)},
        timestamp=started_at,
    )
    if result.status == "succeeded":
        run.tool_count += 1
        completed_event = record_event(
            session,
            run,
            actor="sdk",
            event_type="tool.succeeded",
            summary=result.output_summary or f"{result.name} completed.",
            status="succeeded",
            step_id=result.step_id,
            parent_step_id=result.parent_step_id,
            tool_name=result.name,
            duration_ms=result.duration_ms,
            payload_hash=result.output_hash,
            payload_full=(
                {"output_summary": result.output_summary, **({"output": result.output} if result.output is not None else {})}
                if capture_full
                else None
            ),
            metadata={"call_id": result.call_id, "artifact_count": len(result.artifacts)},
            timestamp=ended_at,
        )
    else:
        run.tool_count += 1
        run.error_count += 1
        completed_event = record_event(
            session,
            run,
            actor="sdk",
            event_type="tool.failed",
            summary=result.error_summary or f"{result.name} failed.",
            status="failed",
            step_id=result.step_id,
            parent_step_id=result.parent_step_id,
            tool_name=result.name,
            duration_ms=result.duration_ms,
            error_code=result.error_code,
            payload_hash=result.output_hash,
            payload_full={"error_summary": result.error_summary} if capture_full else None,
            metadata={"call_id": result.call_id, "artifact_count": len(result.artifacts)},
            timestamp=ended_at,
        )

    for artifact_input in result.artifacts:
        artifact = create_artifact(
            session,
            run,
            source_event_id=completed_event.id,
            kind=artifact_input.kind,
            label=artifact_input.label,
            summary=artifact_input.summary,
            content_hash=stable_hash({"kind": artifact_input.kind, "label": artifact_input.label, "summary": artifact_input.summary}),
            metadata=artifact_input.metadata,
        )
        run.artifact_count += 1
        record_event(
            session,
            run,
            actor="sdk",
            event_type="artifact.created",
            summary=artifact.summary,
            status="created",
            step_id=result.step_id,
            tool_name=result.name,
            artifact_refs=[artifact.id],
            metadata={"artifact_label": artifact.label, "call_id": result.call_id},
            timestamp=ended_at,
        )

    started_event.status = "completed"


def complete_run(
    session: Session,
    run: Run,
    final_output: Any | None,
    artifacts: Sequence[ArtifactInput] = (),
    *,
    ended_at: datetime | None = None,
    capture_full: bool = False,
) -> dict[str, Any]:
    """Mark a run completed, record its final output and derive its explanation.

    The summary of the output is always kept; the whole output only with ``capture_full``.
    """
    final_summary = summarize_value(final_output, sort_keys=False) if final_output is not None else "Run finished without final output."
    run.final_output_summary = final_summary
    run.status = "completed"
    run.ended_at = ended_at or utcnow()
    completed_event = record_event(
        session,
        run,
        actor="proxy",
        event_type="run.completed",
        summary=final_summary,
        status="completed",
        payload_hash=stable_hash(final_output),
        payload_full={"final_output": final_output} if capture_full and final_output is not None else None,
        timestamp=ended_at,
    )
    for artifact_input in artifacts:
        artifact = create_artifact(
            session,
            run,
            source_event_id=completed_event.id,
            kind=artifact_input.kind,
            label=artifact_input.label,
            summary=artifact_input.summary,
            content_hash=stable_hash({"kind": artifact_input.kind, "label": artifact_input.label, "summary": artifact_input.summary}),
            metadata=artifact_input.metadata,
        )
        run.artifact_count += 1
        record_event(
            session,
            run,
            actor="proxy",
            event_type="artifact.created",
            summary=artifact.summary,
            status="created",
            artifact_refs=[artifact.id],
            metadata={"artifact_label": artifact.label},
            timestamp=ended_at,
        )
    return derive_explanation(session, run)


def fail_run_with(
    session: Session,
    run: Run,
    error_code: str,
    error_summary: str,
    *,
    ended_at: datetime | None = None,
) -> None:
    """Mark a run failed, record why and derive its explanation."""
    run.status = "failed"
    run.ended_at = ended_at or utcnow()
    run.error_count += 1
    run.final_output_summary = error_summary
    record_event(
        session,
        run,
        actor="proxy",
        event_type="run.failed",
        summary=error_summary,
        status="failed",
        error_code=error_code,
        payload_hash=stable_hash(error_summary),
        timestamp=ended_at,
    )
    derive_explanation(session, run)


def expire_inactive_runs(session: Session, *, timeout: timedelta, now: datetime | None = None) -> int:
    """Fail the runs that are still running but have had no event for ``timeout``.

    An agent that dies without calling finish or fail would otherwise stay "running" forever and keep
    counting as active. Returns how many runs were closed.
    """
    now = now or utcnow()
    stale = list(session.scalars(select(Run).where(Run.status == "running", Run.updated_at < now - timeout)))
    minutes = max(1, int(timeout.total_seconds() // 60))
    for run in stale:
        fail_run_with(
            session,
            run,
            "RunAbandoned",
            f"No activity for {minutes} minutes: the agent stopped without finishing the run.",
        )
    session.commit()
    return len(stale)
