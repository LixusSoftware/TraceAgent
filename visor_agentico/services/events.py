from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from visor_agentico.models import Artifact, Event, Run


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_event(
    session: Session,
    run: Run,
    *,
    actor: str,
    event_type: str,
    summary: str,
    status: str | None = None,
    step_id: str | None = None,
    parent_step_id: str | None = None,
    duration_ms: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    tool_name: str | None = None,
    artifact_refs: list[Any] | None = None,
    error_code: str | None = None,
    payload_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Event:
    run.last_event_seq += 1
    run.updated_at = utcnow()
    event = Event(
        run_id=run.id,
        seq=run.last_event_seq,
        timestamp=utcnow(),
        step_id=step_id,
        parent_step_id=parent_step_id,
        actor=actor,
        type=event_type,
        summary=summary,
        status=status,
        duration_ms=duration_ms,
        provider=provider,
        model=model,
        tool_name=tool_name,
        artifact_refs=artifact_refs or [],
        error_code=error_code,
        payload_hash=payload_hash,
        event_metadata=metadata or {},
    )
    session.add(event)
    session.flush()
    return event


def create_artifact(
    session: Session,
    run: Run,
    *,
    source_event_id: int | None,
    kind: str,
    label: str,
    summary: str,
    content_hash: str | None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    artifact = Artifact(
        run_id=run.id,
        source_event_id=source_event_id,
        kind=kind,
        label=label,
        summary=summary,
        content_hash=content_hash,
        artifact_metadata=metadata or {},
    )
    session.add(artifact)
    session.flush()
    return artifact

