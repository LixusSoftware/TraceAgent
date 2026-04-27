from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from visor_agentico.models import Artifact, Event, Run


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# In-memory pub/sub for SSE (run_id -> list of queues)
_sse_queues: dict[str, list[asyncio.Queue]] = {}


def _get_sse_queues(run_id: str) -> list[asyncio.Queue]:
    return _sse_queues.get(run_id, [])


def _register_sse_queue(run_id: str, queue: asyncio.Queue) -> None:
    if run_id not in _sse_queues:
        _sse_queues[run_id] = []
    _sse_queues[run_id].append(queue)


def _unregister_sse_queue(run_id: str, queue: asyncio.Queue) -> None:
    if run_id in _sse_queues:
        _sse_queues[run_id] = [q for q in _sse_queues[run_id] if q is not queue]
        if not _sse_queues[run_id]:
            del _sse_queues[run_id]


def _notify_sse_listeners(run_id: str, event_data: dict[str, Any]) -> None:
    queues = _get_sse_queues(run_id)
    for queue in queues:
        try:
            queue.put_nowait(event_data)
        except asyncio.QueueFull:
            pass


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
    payload_full: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> Event:
    run.last_event_seq += 1
    run.updated_at = utcnow()
    event = Event(
        run_id=run.id,
        turn_id=turn_id,
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
        payload_full=payload_full,
        event_metadata=metadata or {},
    )
    session.add(event)
    session.flush()
    _notify_sse_listeners(
        run.id,
        {
            "id": event.id,
            "seq": event.seq,
            "type": event.type,
            "actor": event.actor,
            "summary": event.summary,
            "status": event.status,
            "step_id": event.step_id,
            "tool_name": event.tool_name,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        },
    )
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
