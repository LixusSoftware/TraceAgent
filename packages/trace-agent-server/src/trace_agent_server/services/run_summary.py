from __future__ import annotations

from typing import Any

from trace_agent_server.models import Event, Run


STATE_BY_EVENT_TYPE = {
    "run.started": "initialized",
    "guardrail.input_checked": "guardrail_checked",
    "guardrail.output_checked": "guardrail_checked",
    "guardrail.blocked": "guardrail_blocked",
    "model.requested": "waiting_model",
    "model.responded": "model_responded",
    "tool.requested": "waiting_tool",
    "tool.started": "tool_running",
    "tool.succeeded": "tool_succeeded",
    "tool.failed": "tool_failed",
    "command.started": "command_running",
    "command.succeeded": "command_succeeded",
    "command.failed": "command_failed",
    "file.read": "file_read",
    "file.written": "file_written",
    "patch.applied": "patch_applied",
    "artifact.created": "artifact_created",
    "artifact.updated": "artifact_updated",
    "run.completed": "completed",
    "run.failed": "failed",
}


def _token_usage_template() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
    }


def _registered_tool_count(events: list[Event], run: Run) -> int:
    registered_tools = run.run_metadata.get("registered_tools", [])
    if registered_tools:
        return len(registered_tools)

    for event in reversed(events):
        tool_names = event.event_metadata.get("tool_names")
        if isinstance(tool_names, list) and tool_names:
            return len(tool_names)
        tool_count = event.event_metadata.get("registered_tool_count")
        if isinstance(tool_count, int):
            return tool_count
    return 0


def build_execution_metadata(run: Run, events: list[Event]) -> dict[str, Any]:
    last_event = events[-1] if events else None
    duration_ms: int | None = None
    if run.ended_at is not None:
        duration_ms = max(0, int((run.ended_at - run.started_at).total_seconds() * 1000))
    elif last_event is not None:
        duration_ms = max(0, int((last_event.timestamp - run.started_at).total_seconds() * 1000))

    token_usage = _token_usage_template()
    for event in events:
        if event.type != "model.responded":
            continue
        usage = event.event_metadata.get("usage", {})
        if not isinstance(usage, dict):
            continue
        token_usage["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        token_usage["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        token_usage["total_tokens"] += int(usage.get("total_tokens") or 0)
        completion_details = usage.get("completion_tokens_details", {})
        if isinstance(completion_details, dict):
            token_usage["reasoning_tokens"] += int(completion_details.get("reasoning_tokens") or 0)

    current_state = run.status
    if run.status == "running" and last_event is not None:
        current_state = STATE_BY_EVENT_TYPE.get(last_event.type, run.status)

    return {
        "duration_ms": duration_ms,
        "total_event_count": len(events),
        "model_turn_count": sum(1 for event in events if event.type == "model.requested"),
        "assistant_turn_count": sum(1 for event in events if event.type == "model.responded"),
        "tool_request_count": sum(1 for event in events if event.type == "tool.requested"),
        "tool_success_count": sum(1 for event in events if event.type == "tool.succeeded"),
        "tool_failure_count": sum(1 for event in events if event.type == "tool.failed"),
        "command_count": sum(1 for event in events if event.type in {"command.succeeded", "command.failed"}),
        "command_failure_count": sum(1 for event in events if event.type == "command.failed"),
        "file_read_count": sum(1 for event in events if event.type == "file.read"),
        "file_write_count": sum(1 for event in events if event.type == "file.written"),
        "patch_count": sum(1 for event in events if event.type == "patch.applied"),
        "registered_tool_count": _registered_tool_count(events, run),
        "current_state": current_state,
        "last_event_type": last_event.type if last_event is not None else None,
        "last_event_actor": last_event.actor if last_event is not None else None,
        "last_event_at": last_event.timestamp if last_event is not None else None,
        "token_usage": token_usage,
    }


def build_timeline_groups(events: list[Event]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Event]] = {}
    for event in events:
        key = event.step_id or f"seq-{event.seq}"
        grouped.setdefault(key, []).append(event)

    groups: list[dict[str, Any]] = []
    for step_id, group_events in grouped.items():
        last_event = group_events[-1]
        step_type = "run"
        if any(event.tool_name for event in group_events):
            step_type = "tool"
        elif any(event.type.startswith("command.") for event in group_events):
            step_type = "command"
        elif any(event.type.startswith("file.") for event in group_events):
            step_type = "file"
        elif any(event.type == "patch.applied" for event in group_events):
            step_type = "patch"

        groups.append(
            {
                "step_id": step_id,
                "label": last_event.tool_name or str(last_event.event_metadata.get("path") or last_event.event_metadata.get("command") or last_event.type),
                "status": last_event.status or "observed",
                "step_type": step_type,
                "tool_name": last_event.tool_name,
                "call_id": next(
                    (
                        event.event_metadata.get("call_id")
                        for event in group_events
                        if isinstance(event.event_metadata.get("call_id"), str)
                    ),
                    None,
                ),
                "parent_step_id": next((event.parent_step_id for event in group_events if event.parent_step_id), None),
                "event_count": len(group_events),
                "started_at": group_events[0].timestamp,
                "ended_at": group_events[-1].timestamp,
                "duration_ms": max(
                    0,
                    int((group_events[-1].timestamp - group_events[0].timestamp).total_seconds() * 1000),
                )
                if len(group_events) > 1
                else group_events[-1].duration_ms,
                "events": group_events,
            }
        )

    groups.sort(key=lambda item: item["events"][0].seq if item["events"] else 0)
    return groups


def build_tool_chain(events: list[Event]) -> list[dict[str, Any]]:
    chain: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def get_key(event: Event) -> str:
        call_id = event.event_metadata.get("call_id")
        if isinstance(call_id, str) and call_id:
            return call_id
        if event.step_id:
            return event.step_id
        return f"event-{event.id}"

    for event in events:
        if event.type not in {"tool.requested", "tool.started", "tool.succeeded", "tool.failed", "artifact.created"}:
            continue
        if event.type == "artifact.created" and not event.tool_name and not event.step_id:
            continue

        key = get_key(event)
        if key not in chain:
            chain[key] = {
                "call_id": event.event_metadata.get("call_id") if isinstance(event.event_metadata.get("call_id"), str) else None,
                "step_id": event.step_id or key,
                "parent_step_id": event.parent_step_id,
                "tool_name": event.tool_name or "unknown tool",
                "status": event.status or "observed",
                "event_ids": [],
                "requested_at": None,
                "started_at": None,
                "completed_at": None,
                "duration_ms": None,
                "provider": event.provider,
                "model": event.model,
                "args_summary": None,
                "output_summary": None,
                "error_summary": None,
                "error_code": None,
                "artifact_count": 0,
                "_first_seq": event.seq,
            }
            order.append(key)

        item = chain[key]
        item["event_ids"].append(event.id)
        item["tool_name"] = event.tool_name or item["tool_name"]
        item["provider"] = event.provider or item["provider"]
        item["model"] = event.model or item["model"]
        item["parent_step_id"] = event.parent_step_id or item["parent_step_id"]

        if event.type == "tool.requested":
            item["requested_at"] = event.timestamp
            item["status"] = "requested"
            item["args_summary"] = event.summary
        elif event.type == "tool.started":
            item["started_at"] = event.timestamp
            item["status"] = "running"
            item["args_summary"] = event.event_metadata.get("args_summary") or item["args_summary"]
        elif event.type == "tool.succeeded":
            item["completed_at"] = event.timestamp
            item["duration_ms"] = event.duration_ms
            item["status"] = "succeeded"
            item["output_summary"] = event.summary
        elif event.type == "tool.failed":
            item["completed_at"] = event.timestamp
            item["duration_ms"] = event.duration_ms
            item["status"] = "failed"
            item["error_summary"] = event.summary
            item["error_code"] = event.error_code
        elif event.type == "artifact.created":
            item["artifact_count"] += max(1, len(event.artifact_refs))

    ordered = sorted((chain[key] for key in order), key=lambda item: item["_first_seq"])
    for item in ordered:
        item.pop("_first_seq", None)
    return ordered


def build_command_chain(events: list[Event]) -> list[dict[str, Any]]:
    chain: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def get_key(event: Event) -> str:
        command_id = event.event_metadata.get("command_id")
        if isinstance(command_id, str) and command_id:
            return command_id
        if event.step_id:
            return event.step_id
        return f"command-event-{event.id}"

    for event in events:
        if event.type not in {"command.started", "command.succeeded", "command.failed"}:
            continue

        key = get_key(event)
        if key not in chain:
            chain[key] = {
                "command_id": event.event_metadata.get("command_id") if isinstance(event.event_metadata.get("command_id"), str) else None,
                "step_id": event.step_id or key,
                "parent_step_id": event.parent_step_id,
                "command": str(event.event_metadata.get("command") or "unknown command"),
                "status": event.status or "observed",
                "event_ids": [],
                "started_at": None,
                "completed_at": None,
                "duration_ms": None,
                "cwd": event.event_metadata.get("cwd"),
                "exit_code": event.event_metadata.get("exit_code"),
                "output_summary": None,
                "stdout_summary": None,
                "stderr_summary": None,
                "error_summary": None,
                "error_code": None,
                "_first_seq": event.seq,
            }
            order.append(key)

        item = chain[key]
        item["event_ids"].append(event.id)
        item["parent_step_id"] = event.parent_step_id or item["parent_step_id"]
        item["cwd"] = event.event_metadata.get("cwd") or item["cwd"]
        item["exit_code"] = event.event_metadata.get("exit_code") if event.event_metadata.get("exit_code") is not None else item["exit_code"]
        item["command"] = str(event.event_metadata.get("command") or item["command"])
        item["output_summary"] = event.event_metadata.get("output_summary") or item["output_summary"]
        item["stdout_summary"] = event.event_metadata.get("stdout_summary") or item["stdout_summary"]
        item["stderr_summary"] = event.event_metadata.get("stderr_summary") or item["stderr_summary"]

        if event.type == "command.started":
            item["started_at"] = event.timestamp
            item["status"] = "running"
        elif event.type == "command.succeeded":
            item["completed_at"] = event.timestamp
            item["duration_ms"] = event.duration_ms
            item["status"] = "succeeded"
            item["output_summary"] = event.event_metadata.get("output_summary") or event.summary
        elif event.type == "command.failed":
            item["completed_at"] = event.timestamp
            item["duration_ms"] = event.duration_ms
            item["status"] = "failed"
            item["error_summary"] = event.summary
            item["error_code"] = event.error_code

    ordered = sorted((chain[key] for key in order), key=lambda item: item["_first_seq"])
    for item in ordered:
        item.pop("_first_seq", None)
    return ordered


def build_file_activity(events: list[Event]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in events:
        if event.type not in {"file.read", "file.written"}:
            continue
        items.append(
            {
                "step_id": event.step_id or f"file-{event.id}",
                "parent_step_id": event.parent_step_id,
                "event_id": event.id,
                "event_type": event.type,
                "path": str(event.event_metadata.get("path") or "unknown"),
                "status": event.status or "observed",
                "change_type": event.event_metadata.get("change_type"),
                "summary": event.summary,
                "content_hash": event.event_metadata.get("content_hash"),
                "before_hash": event.event_metadata.get("before_hash"),
                "after_hash": event.event_metadata.get("after_hash"),
                "diff_summary": event.event_metadata.get("diff_summary"),
                "line_additions": event.event_metadata.get("line_additions"),
                "line_deletions": event.event_metadata.get("line_deletions"),
                "extension": event.event_metadata.get("extension"),
                "size_bytes": event.event_metadata.get("size_bytes"),
                "timestamp": event.timestamp,
                "_first_seq": event.seq,
            }
        )

    items.sort(key=lambda item: item["_first_seq"])
    for item in items:
        item.pop("_first_seq", None)
    return items


def build_patch_activity(events: list[Event]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in events:
        if event.type != "patch.applied":
            continue
        items.append(
            {
                "step_id": event.step_id or f"patch-{event.id}",
                "parent_step_id": event.parent_step_id,
                "event_id": event.id,
                "path": str(event.event_metadata.get("path") or "unknown"),
                "status": event.status or "observed",
                "summary": event.summary,
                "before_hash": event.event_metadata.get("before_hash"),
                "after_hash": event.event_metadata.get("after_hash"),
                "diff_summary": event.event_metadata.get("diff_summary"),
                "line_additions": event.event_metadata.get("line_additions"),
                "line_deletions": event.event_metadata.get("line_deletions"),
                "timestamp": event.timestamp,
                "_first_seq": event.seq,
            }
        )

    items.sort(key=lambda item: item["_first_seq"])
    for item in items:
        item.pop("_first_seq", None)
    return items
