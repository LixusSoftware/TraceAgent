from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trace_agent_server.db import get_session
from trace_agent_server.models import Artifact, Decision, Event, Run, Turn
from trace_agent_sdk.redaction import stable_hash, summarize_value
from trace_agent_server.schemas import (
    ArtifactOut,
    DashboardResponse,
    DecisionOut,
    EventOut,
    ExplanationResponse,
    FailRunRequest,
    FinishRunRequest,
    GraphResponse,
    ObservationsRequest,
    RunCreateRequest,
    RunAnalyticsResponse,
    RunCompareResponse,
    RunCreateResponse,
    RunListItem,
    RunOverview,
    TimelineGroup,
    TimelineResponse,
    ToolResultsRequest,
    TurnCreateRequest,
    TurnCreateResponse,
    TurnOut,
)
from trace_agent_server.services.analytics import build_similar_runs, build_tool_graph, build_tool_metrics
from trace_agent_server.services.compare import compare_runs
from trace_agent_server.services.events import create_artifact, record_event
from trace_agent_server.services.explanation import derive_explanation
from trace_agent_server.services.graph import build_decision_graph, build_execution_graph
from trace_agent_server.services.provider import ProviderTurnRequest
from trace_agent_server.services.run_summary import (
    build_command_chain,
    build_execution_metadata,
    build_file_activity,
    build_patch_activity,
    build_timeline_groups,
    build_tool_chain,
)

router = APIRouter(prefix="/api")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_run_or_404(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


def _serialize_event(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        seq=event.seq,
        timestamp=event.timestamp,
        turn_id=event.turn_id,
        step_id=event.step_id,
        parent_step_id=event.parent_step_id,
        actor=event.actor,
        type=event.type,
        summary=event.summary,
        status=event.status,
        duration_ms=event.duration_ms,
        provider=event.provider,
        model=event.model,
        tool_name=event.tool_name,
        artifact_refs=event.artifact_refs,
        error_code=event.error_code,
        payload_hash=event.payload_hash,
        payload_full=event.payload_full,
        metadata=event.event_metadata,
    )


def _serialize_decision(decision: Decision) -> DecisionOut:
    return DecisionOut(
        id=decision.id,
        seq=decision.seq,
        kind=decision.kind,
        label=decision.label,
        chosen_action=decision.chosen_action,
        rationale_summary=decision.rationale_summary,
        trigger_event_ids=decision.trigger_event_ids,
        evidence_event_ids=decision.evidence_event_ids,
        alternatives=decision.alternatives,
        outcome=decision.outcome,
        metadata=decision.decision_metadata,
    )


def _serialize_artifact(artifact: Artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        kind=artifact.kind,
        label=artifact.label,
        summary=artifact.summary,
        metadata=artifact.artifact_metadata,
        source_event_id=artifact.source_event_id,
        created_at=artifact.created_at,
    )


def _serialize_timeline_group(group: dict[str, Any]) -> TimelineGroup:
    return TimelineGroup(
        step_id=group["step_id"],
        label=group["label"],
        status=group["status"],
        step_type=group["step_type"],
        tool_name=group["tool_name"],
        call_id=group["call_id"],
        parent_step_id=group["parent_step_id"],
        event_count=group["event_count"],
        started_at=group["started_at"],
        ended_at=group["ended_at"],
        duration_ms=group["duration_ms"],
        events=[_serialize_event(event) for event in group["events"]],
    )


def _serialize_run_overview(run: Run, events: list[Event]) -> RunOverview:
    return RunOverview(
        id=run.id,
        agent_name=run.agent_name,
        goal=run.goal,
        status=run.status,
        provider=run.provider,
        model=run.model,
        redaction_level=run.redaction_level,
        tool_count=run.tool_count,
        error_count=run.error_count,
        retry_count=run.retry_count,
        artifact_count=run.artifact_count,
        total_prompt_tokens=run.total_prompt_tokens,
        total_completion_tokens=run.total_completion_tokens,
        started_at=run.started_at,
        ended_at=run.ended_at,
        metadata=run.run_metadata,
        final_output_summary=run.final_output_summary,
        flags=run.flag_cache,
        execution=build_execution_metadata(run, events),
        tool_chain=build_tool_chain(events),
        command_chain=build_command_chain(events),
        file_activity=build_file_activity(events),
        patch_activity=build_patch_activity(events),
    )


@router.get("/runs", response_model=list[RunListItem])
def list_runs(
    session: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    agent_name: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    search: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
) -> list[RunListItem]:
    query = select(Run)
    if agent_name:
        query = query.where(Run.agent_name == agent_name)
    if status:
        query = query.where(Run.status == status)
    if provider:
        query = query.where(Run.provider == provider)
    if model:
        query = query.where(Run.model == model)
    if search:
        query = query.where(
            (Run.goal.ilike(f"%{search}%")) | (Run.id.ilike(f"%{search}%"))
        )
    if started_after:
        query = query.where(Run.started_at >= started_after)
    if started_before:
        query = query.where(Run.started_at <= started_before)
    runs = list(session.scalars(query.order_by(Run.started_at.desc()).offset(offset).limit(limit)))
    return [
        RunListItem(
            id=run.id,
            agent_name=run.agent_name,
            goal=run.goal,
            status=run.status,
            started_at=run.started_at,
            ended_at=run.ended_at,
            tool_count=run.tool_count,
            error_count=run.error_count,
            retry_count=run.retry_count,
            artifact_count=run.artifact_count,
            total_prompt_tokens=run.total_prompt_tokens,
            total_completion_tokens=run.total_completion_tokens,
            model=run.model,
            provider=run.provider,
        )
        for run in runs
    ]


@router.post("/runs", response_model=RunCreateResponse)
def create_run(payload: RunCreateRequest, session: Session = Depends(get_session)) -> RunCreateResponse:
    run = Run(agent_name=payload.agent_name, goal=payload.goal, run_metadata=payload.metadata)
    session.add(run)
    session.flush()
    record_event(
        session,
        run,
        actor="proxy",
        event_type="run.started",
        summary=f"Run created for agent {run.agent_name}.",
        status="running",
    )
    session.commit()
    return RunCreateResponse(run_id=run.id, status=run.status)


@router.post("/runs/{run_id}/turns", response_model=TurnCreateResponse)
def create_turn(
    run_id: str,
    payload: TurnCreateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> TurnCreateResponse:
    run = _get_run_or_404(session, run_id)
    if not run.provider:
        run.provider = payload.provider
    if not run.model:
        run.model = payload.model
    registry = request.app.state.provider_registry
    guardrails = getattr(request.app.state, "guardrails", None)
    adapter = registry.get(payload.provider)
    capture_full = getattr(request.app.state.settings, "capture_full_payloads", True)
    if adapter is None:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {payload.provider}")

    sanitized_messages = payload.messages
    input_guardrail_findings: list[dict[str, Any]] = []
    blocked_by_guardrail = False
    guardrail_block_reason: str | None = None
    if guardrails is not None:
        sanitized_messages, input_guardrail_findings, blocked_by_guardrail, guardrail_block_reason = guardrails.sanitize_messages(payload.messages)
        if input_guardrail_findings:
            record_event(
                session,
                run,
                actor="proxy",
                event_type="guardrail.input_checked",
                summary=f"Guardrails found {len(input_guardrail_findings)} input finding(s).",
                status="observed",
                provider=payload.provider,
                model=payload.model,
                metadata={"findings": input_guardrail_findings},
            )
        if blocked_by_guardrail:
            run.error_count += 1
            record_event(
                session,
                run,
                actor="proxy",
                event_type="guardrail.blocked",
                summary=f"Turn blocked by guardrails: {guardrail_block_reason or 'policy'}.",
                status="failed",
                provider=payload.provider,
                model=payload.model,
                error_code="guardrail_blocked",
                metadata={
                    "reason": guardrail_block_reason or "policy",
                    "findings": input_guardrail_findings,
                },
            )
            session.commit()
            raise HTTPException(status_code=400, detail="Input blocked by guardrails.")

    tool_redaction = {tool.name: tool.redact_fields for tool in payload.tools}
    if payload.tools:
        run.run_metadata = {
            **run.run_metadata,
            "registered_tools": [tool.name for tool in payload.tools],
            "registered_tool_descriptions": {tool.name: tool.description for tool in payload.tools},
        }
    message_summary = {
        "message_count": len(sanitized_messages),
        "last_roles": [message.get("role", "unknown") for message in sanitized_messages[-3:]],
    }
    record_event(
        session,
        run,
        actor="proxy",
        event_type="model.requested",
        summary=summarize_value(message_summary),
        status="running",
        provider=payload.provider,
        model=payload.model,
        payload_hash=stable_hash(sanitized_messages),
        payload_full={"messages": sanitized_messages} if capture_full else None,
        metadata={
            "registered_tool_count": len(payload.tools),
            "tool_names": [tool.name for tool in payload.tools],
            "tool_choice": payload.tool_choice,
            "message_count": len(sanitized_messages),
            "guardrail_input_finding_count": len(input_guardrail_findings),
        },
    )

    try:
        response = adapter.generate_turn(
            ProviderTurnRequest(
                model=payload.model,
                messages=sanitized_messages,
                tools=payload.tools,
                tool_choice=payload.tool_choice,
            )
        )
    except Exception as exc:  # pragma: no cover
        run.error_count += 1
        record_event(
            session,
            run,
            actor="provider",
            event_type="run.failed",
            summary=f"Provider error: {exc}",
            status="failed",
            provider=payload.provider,
            model=payload.model,
            error_code="provider_error",
        )
        run.status = "failed"
        run.ended_at = utcnow()
        session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    run.provider = payload.provider
    run.model = payload.model

    # Create Turn record with full messages and token usage
    usage = response.metadata.get("usage", {}) if response.metadata else {}
    turn = Turn(
        run_id=run.id,
        seq=run.last_event_seq + 1,
        provider=payload.provider,
        model=payload.model,
        messages=sanitized_messages,
        assistant_message=response.assistant_message,
        tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments, "step_id": c.step_id} for c in response.tool_calls],
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        reasoning_tokens=usage.get("reasoning_tokens"),
        finish_reason=response.metadata.get("finish_reason") if response.metadata else None,
        response_id=response.metadata.get("response_id") if response.metadata else None,
    )
    session.add(turn)
    session.flush()

    if turn.prompt_tokens:
        run.total_prompt_tokens += turn.prompt_tokens
    if turn.completion_tokens:
        run.total_completion_tokens += turn.completion_tokens

    output_guardrail_findings: list[dict[str, Any]] = []
    if guardrails is not None and response.assistant_message is not None:
        sanitized_assistant_message, output_guardrail_findings = guardrails.sanitize_assistant_message(response.assistant_message)
        response.assistant_message = sanitized_assistant_message
        if output_guardrail_findings:
            record_event(
                session,
                run,
                actor="proxy",
                event_type="guardrail.output_checked",
                summary=f"Guardrails found {len(output_guardrail_findings)} output finding(s).",
                status="observed",
                provider=payload.provider,
                model=payload.model,
                metadata={"findings": output_guardrail_findings},
            )

    response_metadata = dict(response.metadata or {})
    response_metadata["guardrail_output_finding_count"] = len(output_guardrail_findings)
    record_event(
        session,
        run,
        actor="provider",
        event_type="model.responded",
        summary=response.summary,
        status="running",
        provider=payload.provider,
        model=payload.model,
        payload_hash=stable_hash(response.assistant_message or [tool_call.__dict__ for tool_call in response.tool_calls]),
        payload_full={"assistant_message": response.assistant_message, "tool_calls": turn.tool_calls} if capture_full else None,
        turn_id=turn.id,
        metadata=response_metadata,
    )

    tool_calls = []
    for call in response.tool_calls:
        tool_calls.append(call)
        record_event(
            session,
            run,
            actor="provider",
            event_type="tool.requested",
            summary=summarize_value(call.arguments, tool_redaction.get(call.name, [])),
            status="requested",
            step_id=call.step_id,
            parent_step_id=call.parent_step_id,
            provider=payload.provider,
            model=payload.model,
            tool_name=call.name,
            payload_hash=stable_hash(call.arguments),
            payload_full={"arguments": call.arguments} if capture_full else None,
            turn_id=turn.id,
            metadata={"call_id": call.id},
        )

    session.commit()
    if tool_calls:
        return TurnCreateResponse(
            status="requires_action",
            tool_calls=[
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "step_id": call.step_id,
                    "parent_step_id": call.parent_step_id,
                }
                for call in tool_calls
            ],
        )
    return TurnCreateResponse(status="message", assistant_message=response.assistant_message)


@router.post("/runs/{run_id}/tool-results")
def store_tool_results(
    run_id: str,
    payload: ToolResultsRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _get_run_or_404(session, run_id)
    capture_full = getattr(request.app.state.settings, "capture_full_payloads", True)

    for result in payload.results:
        started_event = record_event(
            session,
            run,
            actor="sdk",
            event_type="tool.started",
            summary=f"Started {result.name}.",
            status="running",
            step_id=result.step_id,
            tool_name=result.name,
            payload_hash=stable_hash(result.args),
            payload_full={"args": result.args} if capture_full else None,
            metadata={"call_id": result.call_id, "args_summary": summarize_value(result.args)},
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
                tool_name=result.name,
                duration_ms=result.duration_ms,
                payload_hash=result.output_hash,
                payload_full={"output_summary": result.output_summary} if capture_full else None,
                metadata={"call_id": result.call_id, "artifact_count": len(result.artifacts)},
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
                tool_name=result.name,
                duration_ms=result.duration_ms,
                error_code=result.error_code,
                payload_hash=result.output_hash,
                payload_full={"error_summary": result.error_summary} if capture_full else None,
                metadata={"call_id": result.call_id, "artifact_count": len(result.artifacts)},
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
            )

        started_event.status = "completed"

    session.commit()
    return {"status": "ok", "recorded": len(payload.results)}


@router.post("/runs/{run_id}/observations")
def store_observations(
    run_id: str,
    payload: ObservationsRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _get_run_or_404(session, run_id)
    capture_full = getattr(request.app.state.settings, "capture_full_payloads", True)

    for observation in payload.observations:
        if observation.kind == "command":
            command_id = observation.command_id or observation.step_id or f"command-{run.last_event_seq + 1}"
            command_label = summarize_value(observation.command or "unknown command", max_length=180)
            record_event(
                session,
                run,
                actor="sdk",
                event_type="command.started",
                summary=f"Started command: {command_label}.",
                status="running",
                step_id=observation.step_id or command_id,
                parent_step_id=observation.parent_step_id,
                payload_hash=stable_hash({"command": observation.command, "cwd": observation.cwd}),
                payload_full={"command": observation.command, "cwd": observation.cwd} if capture_full else None,
                metadata={
                    "command_id": command_id,
                    "command": observation.command,
                    "cwd": observation.cwd,
                },
            )
            if observation.status == "failed":
                run.error_count += 1
                record_event(
                    session,
                    run,
                    actor="sdk",
                    event_type="command.failed",
                    summary=observation.error_summary or f"Command failed: {command_label}.",
                    status="failed",
                    step_id=observation.step_id or command_id,
                    parent_step_id=observation.parent_step_id,
                    duration_ms=observation.duration_ms,
                    error_code=observation.error_code,
                    payload_hash=stable_hash({"command": observation.command, "error": observation.error_summary}),
                    payload_full={"command": observation.command, "error_summary": observation.error_summary, "stdout_summary": observation.stdout_summary, "stderr_summary": observation.stderr_summary} if capture_full else None,
                    metadata={
                        "command_id": command_id,
                        "command": observation.command,
                        "cwd": observation.cwd,
                        "exit_code": observation.exit_code,
                        "output_summary": observation.output_summary,
                        "stdout_summary": observation.stdout_summary,
                        "stderr_summary": observation.stderr_summary,
                    },
                )
            else:
                record_event(
                    session,
                    run,
                    actor="sdk",
                    event_type="command.succeeded",
                    summary=observation.output_summary or f"Command succeeded: {command_label}.",
                    status="succeeded",
                    step_id=observation.step_id or command_id,
                    parent_step_id=observation.parent_step_id,
                    duration_ms=observation.duration_ms,
                    payload_hash=stable_hash({"command": observation.command, "output": observation.output_summary}),
                    payload_full={"command": observation.command, "output_summary": observation.output_summary, "stdout_summary": observation.stdout_summary, "stderr_summary": observation.stderr_summary} if capture_full else None,
                    metadata={
                        "command_id": command_id,
                        "command": observation.command,
                        "cwd": observation.cwd,
                        "exit_code": observation.exit_code,
                        "output_summary": observation.output_summary,
                        "stdout_summary": observation.stdout_summary,
                        "stderr_summary": observation.stderr_summary,
                    },
                )
            continue

        if observation.kind == "file_read":
            summary = f"Read {observation.path or 'unknown file'}."
            if observation.size_bytes is not None:
                summary = f"Read {observation.path or 'unknown file'} ({observation.size_bytes} bytes)."
            record_event(
                session,
                run,
                actor="sdk",
                event_type="file.read",
                summary=summary,
                status="observed",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                payload_hash=observation.content_hash,
                payload_full={"path": observation.path, "size_bytes": observation.size_bytes} if capture_full else None,
                metadata={
                    "path": observation.path,
                    "content_hash": observation.content_hash,
                    "size_bytes": observation.size_bytes,
                    "extension": observation.extension,
                    **observation.metadata,
                },
            )
            continue

        if observation.kind == "file_write":
            summary = observation.diff_summary or f"Wrote {observation.path or 'unknown file'}."
            record_event(
                session,
                run,
                actor="sdk",
                event_type="file.written",
                summary=summary,
                status="succeeded",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                payload_hash=observation.after_hash or observation.content_hash,
                payload_full={"path": observation.path, "change_type": observation.change_type, "diff_summary": observation.diff_summary} if capture_full else None,
                metadata={
                    "path": observation.path,
                    "change_type": observation.change_type,
                    "before_hash": observation.before_hash,
                    "after_hash": observation.after_hash,
                    "content_hash": observation.content_hash,
                    "diff_summary": observation.diff_summary,
                    "line_additions": observation.line_additions,
                    "line_deletions": observation.line_deletions,
                    "extension": observation.extension,
                    "size_bytes": observation.size_bytes,
                    **observation.metadata,
                },
            )
            continue

        if observation.kind == "patch":
            record_event(
                session,
                run,
                actor="sdk",
                event_type="patch.applied",
                summary=observation.diff_summary or f"Applied patch to {observation.path or 'unknown file'}.",
                status="succeeded",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                payload_hash=observation.after_hash,
                payload_full={"path": observation.path, "diff_summary": observation.diff_summary} if capture_full else None,
                metadata={
                    "path": observation.path,
                    "before_hash": observation.before_hash,
                    "after_hash": observation.after_hash,
                    "diff_summary": observation.diff_summary,
                    "line_additions": observation.line_additions,
                    "line_deletions": observation.line_deletions,
                    **observation.metadata,
                },
            )
            continue

        if observation.kind == "artifact" and observation.artifact is not None:
            artifact_event = record_event(
                session,
                run,
                actor="sdk",
                event_type="artifact.updated",
                summary=observation.artifact.summary,
                status="created",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                artifact_refs=[],
                payload_hash=observation.artifact.metadata.get("content_hash"),
                metadata={
                    "artifact_label": observation.artifact.label,
                    "artifact_kind": observation.artifact.kind,
                    **observation.metadata,
                },
            )
            artifact = create_artifact(
                session,
                run,
                source_event_id=artifact_event.id,
                kind=observation.artifact.kind,
                label=observation.artifact.label,
                summary=observation.artifact.summary,
                content_hash=observation.artifact.metadata.get("content_hash"),
                metadata=observation.artifact.metadata,
            )
            run.artifact_count += 1
            artifact_event.artifact_refs = [artifact.id]
            continue

        # ── LangChain observation kinds ────────────────────────────────────

        if observation.kind == "chain_step":
            event_type = "chain.started" if observation.status == "running" else "chain.completed"
            if observation.status == "failed":
                event_type = "chain.failed"
            record_event(
                session,
                run,
                actor="sdk",
                event_type=event_type,
                summary=observation.input_summary or f"Chain step: {observation.metadata.get('chain_type', 'unknown')}",
                status=observation.status or "observed",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                duration_ms=observation.duration_ms,
                error_code=observation.error_code,
                payload_hash=stable_hash(observation.metadata),
                payload_full=observation.metadata if capture_full else None,
                metadata=observation.metadata,
            )
            continue

        if observation.kind == "llm_call":
            event_type = "llm.started" if observation.status == "running" else "llm.completed"
            if observation.status == "failed":
                event_type = "llm.failed"
            record_event(
                session,
                run,
                actor="sdk" if observation.status == "running" else "provider",
                event_type=event_type,
                summary=observation.input_summary or f"LLM call via {observation.provider or 'unknown'}",
                status=observation.status or "observed",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                duration_ms=observation.duration_ms,
                provider=observation.provider,
                model=observation.model,
                error_code=observation.error_code,
                payload_hash=stable_hash(observation.metadata),
                payload_full=observation.metadata if capture_full else None,
                metadata={
                    "provider": observation.provider,
                    "model": observation.model,
                    **observation.metadata,
                },
            )
            continue

        if observation.kind == "tool_call":
            event_type = "tool.started" if observation.status == "running" else "tool.succeeded"
            if observation.status == "failed":
                event_type = "tool.failed"
                run.error_count += 1
            record_event(
                session,
                run,
                actor="sdk",
                event_type=event_type,
                summary=observation.input_summary or f"Tool call: {observation.tool_name or 'unknown'}",
                status=observation.status or "observed",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                tool_name=observation.tool_name,
                duration_ms=observation.duration_ms,
                error_code=observation.error_code,
                payload_hash=stable_hash(observation.metadata),
                payload_full=observation.metadata if capture_full else None,
                metadata={
                    "tool_name": observation.tool_name,
                    **observation.metadata,
                },
            )
            continue

        if observation.kind == "retriever_query":
            event_type = "retriever.queried" if observation.status == "running" else "retriever.responded"
            if observation.status == "failed":
                event_type = "retriever.failed"
            record_event(
                session,
                run,
                actor="sdk",
                event_type=event_type,
                summary=observation.input_summary or f"Retriever query",
                status=observation.status or "observed",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                duration_ms=observation.duration_ms,
                error_code=observation.error_code,
                payload_hash=stable_hash(observation.metadata),
                payload_full=observation.metadata if capture_full else None,
                metadata=observation.metadata,
            )
            continue

        if observation.kind == "agent_action":
            event_type = "agent.action" if observation.status == "running" else "agent.finish"
            if observation.status == "failed":
                event_type = "agent.failed"
            record_event(
                session,
                run,
                actor="sdk",
                event_type=event_type,
                summary=observation.input_summary or f"Agent action",
                status=observation.status or "observed",
                step_id=observation.step_id,
                parent_step_id=observation.parent_step_id,
                tool_name=observation.tool_name,
                duration_ms=observation.duration_ms,
                error_code=observation.error_code,
                payload_hash=stable_hash(observation.metadata),
                payload_full=observation.metadata if capture_full else None,
                metadata={
                    "tool_name": observation.tool_name,
                    **observation.metadata,
                },
            )
            continue

    session.commit()
    return {"status": "ok", "recorded": len(payload.observations)}


@router.post("/runs/{run_id}/finish")
def finish_run(
    run_id: str,
    payload: FinishRunRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _get_run_or_404(session, run_id)
    final_summary = summarize_value(payload.final_output) if payload.final_output is not None else "Run finished without final output."
    run.final_output_summary = final_summary
    run.status = "completed"
    run.ended_at = utcnow()
    completed_event = record_event(
        session,
        run,
        actor="proxy",
        event_type="run.completed",
        summary=final_summary,
        status="completed",
        payload_hash=stable_hash(payload.final_output),
    )
    for artifact_input in payload.artifacts:
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
        )
    derivation = derive_explanation(session, run)
    session.commit()
    return {"status": "completed", "run_id": run.id, "decisions": len(derivation["decisions"])}


@router.post("/runs/{run_id}/fail")
def fail_run(
    run_id: str,
    payload: FailRunRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = _get_run_or_404(session, run_id)
    run.status = "failed"
    run.ended_at = utcnow()
    run.error_count += 1
    run.final_output_summary = payload.error_summary
    record_event(
        session,
        run,
        actor="proxy",
        event_type="run.failed",
        summary=payload.error_summary,
        status="failed",
        error_code=payload.error_code,
        payload_hash=stable_hash(payload.error_summary),
    )
    derive_explanation(session, run)
    session.commit()
    return {"status": "failed", "run_id": run.id}


@router.get("/runs/{run_id}/analytics", response_model=RunAnalyticsResponse)
def get_run_analytics(
    run_id: str,
    request: Request,
    same_agent_only: bool = Query(default=False),
    status: str | None = Query(default=None, pattern="^(completed|failed|running)$"),
    shared_tools_only: bool = Query(default=False),
    min_score: float = Query(default=0.15, ge=0.0, le=1.0),
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
) -> RunAnalyticsResponse:
    run = _get_run_or_404(session, run_id)
    events = list(session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.seq)))
    tool_chain = build_tool_chain(events)
    tool_graph = build_tool_graph(tool_chain)
    settings = request.app.state.settings
    return RunAnalyticsResponse(
        run_id=run_id,
        tool_graph=GraphResponse(run_id=run_id, view="tool_chain", nodes=tool_graph["nodes"], edges=tool_graph["edges"]),
        tool_metrics=build_tool_metrics(events, tool_chain, settings),
        similar_runs=build_similar_runs(
            session,
            run,
            tool_chain,
            limit=limit,
            same_agent_only=same_agent_only,
            status_filter=status,
            shared_tools_only=shared_tools_only,
            min_score=min_score,
        ),
    )


@router.get("/runs/compare", response_model=RunCompareResponse)
def get_run_compare(
    left_run_id: str,
    right_run_id: str,
    session: Session = Depends(get_session),
) -> RunCompareResponse:
    left_run = _get_run_or_404(session, left_run_id)
    right_run = _get_run_or_404(session, right_run_id)

    if not left_run.explanation_cache and left_run.status in {"completed", "failed"}:
        derive_explanation(session, left_run)
    if not right_run.explanation_cache and right_run.status in {"completed", "failed"}:
        derive_explanation(session, right_run)
    session.flush()

    left_events = list(session.scalars(select(Event).where(Event.run_id == left_run_id).order_by(Event.seq)))
    right_events = list(session.scalars(select(Event).where(Event.run_id == right_run_id).order_by(Event.seq)))
    left_artifacts = list(session.scalars(select(Artifact).where(Artifact.run_id == left_run_id).order_by(Artifact.created_at)))
    right_artifacts = list(session.scalars(select(Artifact).where(Artifact.run_id == right_run_id).order_by(Artifact.created_at)))
    left_decisions = list(session.scalars(select(Decision).where(Decision.run_id == left_run_id).order_by(Decision.seq)))
    right_decisions = list(session.scalars(select(Decision).where(Decision.run_id == right_run_id).order_by(Decision.seq)))

    comparison = compare_runs(
        left_run=left_run,
        right_run=right_run,
        left_events=left_events,
        right_events=right_events,
        left_artifacts=left_artifacts,
        right_artifacts=right_artifacts,
        left_decisions=left_decisions,
        right_decisions=right_decisions,
    )
    return RunCompareResponse(
        left_run=_serialize_run_overview(left_run, left_events),
        right_run=_serialize_run_overview(right_run, right_events),
        overview_diff=comparison["overview_diff"],
        divergence=comparison["divergence"],
        aligned_timeline=comparison["aligned_timeline"],
        tool_diff=comparison["tool_diff"],
        command_diff=comparison["command_diff"],
        file_diff=comparison["file_diff"],
        artifact_diff=comparison["artifact_diff"],
        decision_diff=comparison["decision_diff"],
        root_cause=comparison["root_cause"],
        evidence={
            "left": {str(event.id): _serialize_event(event) for event in left_events},
            "right": {str(event.id): _serialize_event(event) for event in right_events},
        },
    )


@router.get("/runs/{run_id}", response_model=RunOverview)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunOverview:
    run = _get_run_or_404(session, run_id)
    events = list(session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.seq)))
    return _serialize_run_overview(run, events)


@router.get("/runs/{run_id}/timeline", response_model=TimelineResponse)
def get_timeline(run_id: str, session: Session = Depends(get_session)) -> TimelineResponse:
    _get_run_or_404(session, run_id)
    events = list(session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.seq)))
    groups = [_serialize_timeline_group(group) for group in build_timeline_groups(events)]
    return TimelineResponse(run_id=run_id, groups=groups)


@router.get("/runs/{run_id}/graph", response_model=GraphResponse)
def get_graph(
    run_id: str,
    view: str = Query(default="execution", pattern="^(execution|decisions)$"),
    session: Session = Depends(get_session),
) -> GraphResponse:
    _get_run_or_404(session, run_id)
    if view == "execution":
        events = list(session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.seq)))
        artifacts = list(session.scalars(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)))
        graph = build_execution_graph(events, artifacts)
    else:
        decisions = list(session.scalars(select(Decision).where(Decision.run_id == run_id).order_by(Decision.seq)))
        graph = build_decision_graph(decisions)
    return GraphResponse(run_id=run_id, view=view, nodes=graph["nodes"], edges=graph["edges"])


@router.get("/runs/{run_id}/explanation", response_model=ExplanationResponse)
def get_explanation(run_id: str, session: Session = Depends(get_session)) -> ExplanationResponse:
    run = _get_run_or_404(session, run_id)
    if not run.explanation_cache and run.status in {"completed", "failed"}:
        derive_explanation(session, run)
        session.commit()

    decisions = list(session.scalars(select(Decision).where(Decision.run_id == run_id).order_by(Decision.seq)))
    events = list(session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.seq)))
    evidence = {str(event.id): _serialize_event(event) for event in events}
    return ExplanationResponse(
        run_id=run_id,
        narrative=run.explanation_cache.get("narrative", []),
        decisions=[_serialize_decision(decision) for decision in decisions],
        flags=run.flag_cache,
        evidence=evidence,
    )


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactOut])
def get_artifacts(run_id: str, session: Session = Depends(get_session)) -> list[ArtifactOut]:
    _get_run_or_404(session, run_id)
    artifacts = list(session.scalars(select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)))
    return [_serialize_artifact(artifact) for artifact in artifacts]


@router.get("/runs/{run_id}/audit")
def get_run_audit(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Return a structured audit report for a run based on guardrail events."""
    run = _get_run_or_404(session, run_id)
    events = list(session.scalars(select(Event).where(Event.run_id == run_id).order_by(Event.seq)))

    GUARDRAIL_TYPES = {"guardrail.input_checked", "guardrail.output_checked", "guardrail.blocked"}
    guardrail_events: list[dict[str, Any]] = []
    pii_hit_count = 0
    injection_hit_count = 0
    secret_hit_count = 0
    block_count = 0

    for event in events:
        if event.type not in GUARDRAIL_TYPES:
            continue

        metadata = event.event_metadata or {}
        findings: list[dict[str, Any]] = metadata.get("findings") or []

        for finding in findings:
            kind = finding.get("kind", "")
            if kind == "pii":
                pii_hit_count += 1
            elif kind == "prompt_injection":
                injection_hit_count += 1
            elif kind == "secret":
                secret_hit_count += 1

        if event.type == "guardrail.blocked":
            block_count += 1

        scope = "block" if event.type == "guardrail.blocked" else ("input" if "input" in event.type else "output")
        severities = [f.get("severity", "medium") for f in findings]
        max_severity = "high" if "high" in severities else ("medium" if "medium" in severities else "low")

        guardrail_events.append({
            "event_id": event.id,
            "seq": event.seq,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "type": event.type,
            "scope": scope,
            "summary": event.summary,
            "severity": max_severity if findings else "info",
            "finding_count": len(findings),
            "findings": findings,
            "provider": event.provider,
            "model": event.model,
        })

    total_issues = pii_hit_count + injection_hit_count + secret_hit_count + block_count
    if total_issues == 0:
        security_score = 100
    else:
        penalty = min(100, (block_count * 20) + (injection_hit_count * 10) + (secret_hit_count * 8) + (pii_hit_count * 3))
        security_score = max(0, 100 - penalty)

    return {
        "run_id": run_id,
        "security_score": security_score,
        "pii_hit_count": pii_hit_count,
        "injection_hit_count": injection_hit_count,
        "secret_hit_count": secret_hit_count,
        "block_count": block_count,
        "guardrail_event_count": len(guardrail_events),
        "guardrail_events": guardrail_events,
        "flags": run.flag_cache or [],
    }



@router.get("/runs/{run_id}/events/stream")
async def stream_events(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    _get_run_or_404(session, run_id)
    from trace_agent_server.services.events import _register_sse_queue, _unregister_sse_queue

    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _register_sse_queue(run_id, queue)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"
            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            _unregister_sse_queue(run_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    period: str = Query(default="24h", pattern="^(24h|7d|30d)$"),
    session: Session = Depends(get_session),
) -> DashboardResponse:
    from trace_agent_server.services.dashboard import build_dashboard
    return build_dashboard(session, period)


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
def list_run_events(
    run_id: str,
    type: str | None = None,
    status: str | None = None,
    actor: str | None = None,
    tool_name: str | None = None,
    step_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    _get_run_or_404(session, run_id)
    query = select(Event).where(Event.run_id == run_id)
    if type:
        query = query.where(Event.type == type)
    if status:
        query = query.where(Event.status == status)
    if actor:
        query = query.where(Event.actor == actor)
    if tool_name:
        query = query.where(Event.tool_name == tool_name)
    if step_id:
        query = query.where(Event.step_id == step_id)
    events = list(session.scalars(query.order_by(Event.seq).offset(offset).limit(limit)))
    return [_serialize_event(e) for e in events]


@router.get("/runs/{run_id}/turns", response_model=list[TurnOut])
def list_run_turns(
    run_id: str,
    session: Session = Depends(get_session),
) -> list[TurnOut]:
    _get_run_or_404(session, run_id)
    turns = list(session.scalars(select(Turn).where(Turn.run_id == run_id).order_by(Turn.seq)))
    return [TurnOut.model_validate(t) for t in turns]
