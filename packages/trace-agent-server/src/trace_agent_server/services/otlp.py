"""Turn OpenTelemetry GenAI spans into TraceAgent runs and events.

Agents instrumented with OpenTelemetry (Pydantic AI's ``Instrumentation`` and any other
framework following the GenAI semantic conventions) export spans; this module replays them
as the same events the REST integrations produce, so the rest of TraceAgent (timeline,
graph, decisions, analytics, dashboard) works unchanged.

Span mapping, by ``gen_ai.operation.name``:

* ``invoke_agent`` -> ``chain.started`` / ``chain.completed`` or ``chain.failed``
* ``chat``         -> ``llm.started`` / ``llm.completed`` or ``llm.failed``
* ``execute_tool`` -> ``tool.started`` / ``tool.succeeded`` or ``tool.failed``

Any other span (HTTP servers, databases...) is ignored.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from trace_agent_sdk.redaction import redact_payload, stable_hash, summarize_value
from trace_agent_server.models import Event, Run
from trace_agent_server.schemas import ToolResultInput
from trace_agent_server.services.events import record_event
from trace_agent_server.services.explanation import derive_explanation
from trace_agent_server.services.otlp_decode import SpanRecord
from trace_agent_server.services.run_lifecycle import (
    apply_llm_usage,
    complete_run,
    fail_run_with,
    record_tool_result,
)

ACTOR = "otlp"
OPERATIONS = ("invoke_agent", "chat", "execute_tool")
RUN_ID_ATTRIBUTE = "trace_agent.run_id"
AGENT_CALL_ID = "gen_ai.agent.call.id"
DEFAULT_GOAL = "OpenTelemetry trace"


@dataclass
class IngestResult:
    ingested: int = 0  # spans turned into events
    duplicates: int = 0  # spans already recorded by an earlier delivery of the same batch
    ignored: int = 0  # spans that are not GenAI operations
    rejected: int = 0  # spans that could not be understood
    run_ids: set[str] = field(default_factory=set)


@dataclass
class _Step:
    """One recorded unit of work, placed on the timeline at ``time``.

    When two steps share an instant, the one that ends goes first (``ends_first``), as the
    next step can only begin once the previous one is over.
    """

    time: datetime
    apply: Callable[[], None]
    ends_first: bool = False

    @property
    def sort_key(self) -> tuple[datetime, int]:
        return self.time, 0 if self.ends_first else 1


# ── Span reading helpers ─────────────────────────────────────────────────────


def operation(span: SpanRecord) -> str | None:
    value = span.attributes.get("gen_ai.operation.name")
    return value if value in OPERATIONS else None


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def _readable(text: Any) -> Any:
    """Decode the \\uXXXX escapes of a JSON text, so accents show as typed.

    Some producers serialize results with json.dumps defaults, which escapes every non-ASCII character.
    """
    if isinstance(text, str) and "\\u" in text:
        parsed = _parse_json(text)
        if parsed is not text:
            return parsed
    return text


def _error_of(span: SpanRecord) -> tuple[str, str]:
    """Error code (the exception class name) and message of a failed span."""
    for event in span.events:
        if event.name == "exception":
            kind = str(event.attributes.get("exception.type") or "Error")
            message = str(event.attributes.get("exception.message") or span.status_message or kind)
            return kind.rsplit(".", 1)[-1], message
    return "Error", span.status_message or "Span failed."


def _first_user_text(input_messages: Any) -> str | None:
    for message in input_messages if isinstance(input_messages, list) else []:
        if isinstance(message, dict) and message.get("role") == "user":
            for part in message.get("parts", []):
                if isinstance(part, dict) and part.get("type") == "text" and part.get("content"):
                    return str(part["content"])
    return None


def _requested_tools(output_messages: Any) -> list[str]:
    names: list[str] = []
    for message in output_messages if isinstance(output_messages, list) else []:
        for part in message.get("parts", []) if isinstance(message, dict) else []:
            if isinstance(part, dict) and part.get("type") == "tool_call" and part.get("name"):
                names.append(str(part["name"]))
    return names


def _run_key(session: Session, span: SpanRecord) -> str | None:
    """The run a span belongs to: an explicitly named existing run, else one per trace."""
    named = span.attributes.get(RUN_ID_ATTRIBUTE) or span.resource.get(RUN_ID_ATTRIBUTE)
    if isinstance(named, str) and named and session.get(Run, named) is not None:
        return named
    try:
        # A trace id is 128 bits, exactly the size of a UUID: the run is found by primary key
        # in any batch, and after restarts, without storing a mapping.
        return str(UUID(hex=span.trace_id))
    except ValueError:
        return None


# ── Ingestion ────────────────────────────────────────────────────────────────


def ingest_spans(session: Session, spans: list[SpanRecord], *, capture_full: bool) -> IngestResult:
    """Record a batch of exported spans. The caller commits the session."""
    result = IngestResult()
    by_run: dict[str, list[SpanRecord]] = {}
    for span in spans:
        if operation(span) is None:
            result.ignored += 1
            continue
        key = _run_key(session, span)
        if key is None:
            result.rejected += 1
            continue
        by_run.setdefault(key, []).append(span)

    for run_id, run_spans in sorted(by_run.items(), key=lambda item: min(s.start for s in item[1])):
        _ingest_run(session, run_id, run_spans, capture_full, result)
        result.run_ids.add(run_id)
    return result


def _ingest_run(session: Session, run_id: str, spans: list[SpanRecord], capture_full: bool, result: IngestResult) -> None:
    already_recorded = set(
        session.scalars(select(Event.step_id).where(Event.run_id == run_id, Event.step_id.in_([s.span_id for s in spans])))
    )
    fresh = [s for s in spans if s.span_id not in already_recorded]
    result.duplicates += len(spans) - len(fresh)
    if not fresh:
        return

    run = session.get(Run, run_id)
    if run is None:
        run = _create_run(session, run_id, fresh)
    else:
        _pull_back_start(session, run, min(s.start for s in fresh))
    was_open = run.status == "running"

    steps: list[_Step] = []
    for span in fresh:
        try:
            steps.extend(_steps_for(session, run, span, capture_full))
            result.ingested += 1
        except Exception:  # noqa: BLE001 - one malformed span must not drop the rest of the batch
            result.rejected += 1
    # Spans arrive when they end, in batches: replay them in the order they happened.
    for step in sorted(steps, key=lambda s: s.sort_key):
        step.apply()
    _renumber_chronologically(session, run)

    _track_agent_calls(run, fresh)
    closing = _closing_span(run, fresh) if was_open else None
    if closing is not None:
        _close_run(session, run, closing)
    elif not was_open:
        # Late spans of a finished run: refresh its decisions and flags.
        derive_explanation(session, run)


def _create_run(session: Session, run_id: str, spans: list[SpanRecord]) -> Run:
    first = min(spans, key=lambda s: s.start)
    named = next((s for s in sorted(spans, key=lambda s: s.start) if s.attributes.get("gen_ai.agent.name")), None)
    agent_name = str(named.attributes["gen_ai.agent.name"]) if named else str(first.resource.get("service.name") or "unknown-agent")
    prompt = next(
        (
            text
            for s in sorted(spans, key=lambda s: s.start)
            if operation(s) == "chat" and (text := _first_user_text(_parse_json(s.attributes.get("gen_ai.input.messages"))))
        ),
        None,
    )
    run = Run(
        id=run_id,
        agent_name=agent_name[:255],
        goal=summarize_value(prompt, max_length=500) if prompt else DEFAULT_GOAL,
        run_metadata={
            "source": "otlp",
            "trace_id": first.trace_id,
            "service_name": first.resource.get("service.name"),
        },
        started_at=first.start,
    )
    session.add(run)
    session.flush()
    record_event(
        session,
        run,
        actor="proxy",
        event_type="run.started",
        summary=f"Run created for agent {run.agent_name}.",
        status="running",
        timestamp=first.start,
    )
    return run


def _start_and_end(span: SpanRecord, started: Callable[[], None], ended: Callable[[], None]) -> list[_Step]:
    # A span with no duration ends at the instant it starts: keep its end after its own start.
    return [_Step(span.start, started), _Step(span.end, ended, ends_first=span.end > span.start)]


def _steps_for(session: Session, run: Run, span: SpanRecord, capture_full: bool) -> list[_Step]:
    kind = operation(span)
    if kind == "invoke_agent":
        return _agent_steps(session, run, span, capture_full)
    if kind == "chat":
        return _model_steps(session, run, span, capture_full)
    return _tool_steps(session, run, span, capture_full)


def _agent_steps(session: Session, run: Run, span: SpanRecord, capture_full: bool) -> list[_Step]:
    name = str(span.attributes.get("gen_ai.agent.name") or "agent")
    failed = span.status_code == "ERROR"
    usage = {
        "prompt_tokens": span.attributes.get("gen_ai.aggregated_usage.input_tokens"),
        "completion_tokens": span.attributes.get("gen_ai.aggregated_usage.output_tokens"),
    }
    metadata = {
        "agent_name": name,
        "agent_call_id": span.attributes.get(AGENT_CALL_ID),
        "conversation_id": span.attributes.get("gen_ai.conversation.id"),
        **{key: value for key, value in usage.items() if value is not None},
    }
    final = span.attributes.get("final_result")

    def started() -> None:
        record_event(
            session, run, actor=ACTOR, event_type="chain.started", summary=f"Agent run '{name}' started",
            status="running", step_id=span.span_id, parent_step_id=span.parent_span_id,
            metadata=metadata, timestamp=span.start,
        )

    def ended() -> None:
        code, message = _error_of(span) if failed else (None, None)
        record_event(
            session, run, actor=ACTOR,
            event_type="chain.failed" if failed else "chain.completed",
            summary=message if failed else f"Agent run '{name}' completed",
            status="failed" if failed else "succeeded",
            step_id=span.span_id, parent_step_id=span.parent_span_id, duration_ms=span.duration_ms,
            error_code=code, payload_hash=stable_hash(final),
            payload_full={"final_result": final} if capture_full and final is not None else None,
            metadata={**metadata, "output_summary": summarize_value(final)} if final is not None else metadata,
            timestamp=span.end,
        )

    return _start_and_end(span, started, ended)


def _model_steps(session: Session, run: Run, span: SpanRecord, capture_full: bool) -> list[_Step]:
    attributes = span.attributes
    provider = attributes.get("gen_ai.provider.name") or attributes.get("gen_ai.system")
    request_model = attributes.get("gen_ai.request.model")
    model = attributes.get("gen_ai.response.model") or request_model
    prompt_tokens = attributes.get("gen_ai.usage.input_tokens")
    completion_tokens = attributes.get("gen_ai.usage.output_tokens")
    failed = span.status_code == "ERROR"
    output_messages = _parse_json(attributes.get("gen_ai.output.messages"))
    metadata = {
        "agent_call_id": attributes.get(AGENT_CALL_ID),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (prompt_tokens or 0) + (completion_tokens or 0) if prompt_tokens or completion_tokens else None,
        "finish_reasons": attributes.get("gen_ai.response.finish_reasons"),
        "requested_tools": _requested_tools(output_messages),
    }
    metadata = {key: value for key, value in metadata.items() if value not in (None, [])}
    provider_text = str(provider)[:64] if provider else None
    model_text = str(model)[:128] if model else None

    def started() -> None:
        record_event(
            session, run, actor=ACTOR, event_type="llm.started", summary=f"Model request to {request_model or 'model'}",
            status="running", step_id=span.span_id, parent_step_id=span.parent_span_id,
            provider=provider_text, model=model_text, metadata={"agent_call_id": attributes.get(AGENT_CALL_ID)},
            timestamp=span.start,
        )

    def ended() -> None:
        code, message = _error_of(span) if failed else (None, None)
        if not failed:
            apply_llm_usage(run, provider=provider_text, model=model_text, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        payload = None
        if capture_full:
            payload = {
                "input_messages": _parse_json(attributes.get("gen_ai.input.messages")),
                "output_messages": output_messages,
            }
        record_event(
            session, run, actor=ACTOR if failed else "provider",
            event_type="llm.failed" if failed else "llm.completed",
            summary=message if failed else f"Model responded via {provider_text or 'provider'}",
            status="failed" if failed else "succeeded",
            step_id=span.span_id, parent_step_id=span.parent_span_id, duration_ms=span.duration_ms,
            provider=provider_text, model=model_text, error_code=code,
            payload_hash=stable_hash(output_messages), payload_full=payload,
            metadata=metadata, timestamp=span.end,
        )

    return _start_and_end(span, started, ended)


def _tool_steps(session: Session, run: Run, span: SpanRecord, capture_full: bool) -> list[_Step]:
    attributes = span.attributes
    name = str(attributes.get("gen_ai.tool.name") or "unknown tool")
    failed = span.status_code == "ERROR"
    arguments = _parse_json(attributes.get("gen_ai.tool.call.arguments"))
    result_text = attributes.get("gen_ai.tool.call.result")
    code, message = _error_of(span) if failed else (None, None)
    tool_result = ToolResultInput(
        call_id=str(attributes.get("gen_ai.tool.call.id") or span.span_id),
        name=name,
        step_id=span.span_id,
        parent_step_id=span.parent_span_id,
        status="failed" if failed else "succeeded",
        args=redact_payload(arguments if isinstance(arguments, dict) else {"input": arguments} if arguments is not None else {}),
        output_summary=summarize_value(_readable(result_text)) if result_text is not None else None,
        output_hash=stable_hash(result_text if not failed else {"error": message}),
        error_code=code,
        error_summary=message,
        duration_ms=span.duration_ms,
    )

    # A tool is recorded as one unit (started and completed events together), placed at its start.
    def record() -> None:
        record_tool_result(session, run, tool_result, capture_full=capture_full, started_at=span.start, ended_at=span.end)

    return [_Step(span.start, record)]


def _pull_back_start(session: Session, run: Run, earliest: datetime) -> None:
    """Move the start of the run back when spans from before it arrive late.

    The agent span, the first thing that happened, is exported last: the run was created
    from whichever span ended first and has to start no later than the earliest span.
    """
    if run.run_metadata.get("source") != "otlp":
        return
    stored = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=earliest.tzinfo)
    if earliest >= stored:
        return
    run.started_at = earliest
    started = session.scalars(select(Event).where(Event.run_id == run.id, Event.type == "run.started")).first()
    if started is not None:
        started.timestamp = earliest


def _renumber_chronologically(session: Session, run: Run) -> None:
    """Make ``seq`` follow the time events happened, not the time they arrived.

    Spans are exported when they end, so an agent span (the first thing that happened)
    arrives after everything it did, and a slow batch can arrive after a newer one. Everything
    that reads a run in ``seq`` order (timeline, graph, decisions) needs the real order.
    Only runs this receiver built are renumbered: a run it was merely attached to also has
    events from other sources, stamped with a different clock.
    """
    if run.run_metadata.get("source") != "otlp":
        return
    events = list(session.scalars(select(Event).where(Event.run_id == run.id).order_by(Event.timestamp, Event.seq)))
    if [event.seq for event in events] == sorted(event.seq for event in events):
        return
    # (run_id, seq) is unique: park every event on a free number first, then number them for good.
    for index, event in enumerate(events, start=1):
        event.seq = -index
    session.flush()
    for index, event in enumerate(events, start=1):
        event.seq = index
    run.last_event_seq = len(events)
    session.flush()


# ── Ending the run ───────────────────────────────────────────────────────────


def _track_agent_calls(run: Run, spans: list[SpanRecord]) -> None:
    """Remember which agent runs have shown activity and which have ended, across batches."""
    state = dict(run.run_metadata.get("otlp") or {})
    seen = set(state.get("seen_calls", []))
    ended = set(state.get("ended_calls", []))
    for span in spans:
        call_id = span.attributes.get(AGENT_CALL_ID)
        if not call_id:
            continue
        seen.add(str(call_id))
        if operation(span) == "invoke_agent":
            ended.add(str(call_id))
    state.update(seen_calls=sorted(seen), ended_calls=sorted(ended))
    # Reassign: the JSON column does not notice in-place changes.
    run.run_metadata = {**run.run_metadata, "otlp": state}


def _closing_span(run: Run, spans: list[SpanRecord]) -> SpanRecord | None:
    """The agent span that ends the run: the last to finish once no agent call is left open.

    Nested agents end before the agent that called them, and an agent behind a web server
    has a parent span of its own, so "the span without a parent" is not a reliable end.
    """
    state = run.run_metadata.get("otlp") or {}
    still_open = set(state.get("seen_calls", [])) - set(state.get("ended_calls", []))
    agents = [s for s in spans if operation(s) == "invoke_agent"]
    if still_open or not agents:
        return None
    return max(agents, key=lambda s: s.end)


def _close_run(session: Session, run: Run, span: SpanRecord) -> None:
    if span.status_code == "ERROR":
        code, message = _error_of(span)
        fail_run_with(session, run, code, message, ended_at=span.end)
    else:
        complete_run(session, run, span.attributes.get("final_result"), ended_at=span.end)
