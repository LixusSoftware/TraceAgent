from __future__ import annotations

from typing import Any

from visor_agentico.models import Artifact, Decision, Event, Run
from visor_agentico.services.run_summary import (
    build_command_chain,
    build_file_activity,
    build_patch_activity,
    build_timeline_groups,
    build_tool_chain,
)


def _event_map(events: list[Event]) -> dict[int, Event]:
    return {event.id: event for event in events}


def _first_seq(event_ids: list[int], lookup: dict[int, Event]) -> int:
    seqs = [lookup[event_id].seq for event_id in event_ids if event_id in lookup]
    return min(seqs) if seqs else 10**9


def _target(
    *,
    label: str,
    status: str | None,
    summary: str | None,
    event_ids: list[int],
    step_id: str | None,
    duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "status": status,
        "summary": summary,
        "event_ids": event_ids,
        "step_id": step_id,
        "duration_ms": duration_ms,
        "metadata": metadata or {},
    }


def _normalize_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _pair_summary(kind: str, relation: str, left_label: str | None, right_label: str | None) -> str:
    if relation == "shared":
        return f"Shared {kind}: {left_label or right_label}."
    if relation == "left_only":
        return f"Only left run used {kind}: {left_label}."
    if relation == "right_only":
        return f"Only right run used {kind}: {right_label}."
    if left_label == right_label:
        return f"Same {kind} with a different outcome: {left_label}."
    return f"{kind.title()} diverged: {left_label or 'none'} vs {right_label or 'none'}."


def _align_sequence(
    left_items: list[dict[str, Any]],
    right_items: list[dict[str, Any]],
    *,
    kind: str,
    label_key: str,
    step_key: str = "step_id",
    status_key: str = "status",
    summary_keys: tuple[str, ...],
    metadata_builder,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    left_index = 0
    right_index = 0

    while left_index < len(left_items) or right_index < len(right_items):
        left_item = left_items[left_index] if left_index < len(left_items) else None
        right_item = right_items[right_index] if right_index < len(right_items) else None

        if left_item is None and right_item is not None:
            right_label = str(right_item.get(label_key) or "unknown")
            pairs.append(
                {
                    "relation": "right_only",
                    "kind": kind,
                    "summary": _pair_summary(kind, "right_only", None, right_label),
                    "left": None,
                    "right": _target(
                        label=right_label,
                        status=right_item.get(status_key),
                        summary=next((right_item.get(key) for key in summary_keys if right_item.get(key)), None),
                        event_ids=list(right_item.get("event_ids", [right_item.get("event_id")]).copy()),
                        step_id=right_item.get(step_key),
                        duration_ms=right_item.get("duration_ms"),
                        metadata=metadata_builder(right_item),
                    ),
                }
            )
            right_index += 1
            continue

        if right_item is None and left_item is not None:
            left_label = str(left_item.get(label_key) or "unknown")
            pairs.append(
                {
                    "relation": "left_only",
                    "kind": kind,
                    "summary": _pair_summary(kind, "left_only", left_label, None),
                    "left": _target(
                        label=left_label,
                        status=left_item.get(status_key),
                        summary=next((left_item.get(key) for key in summary_keys if left_item.get(key)), None),
                        event_ids=list(left_item.get("event_ids", [left_item.get("event_id")]).copy()),
                        step_id=left_item.get(step_key),
                        duration_ms=left_item.get("duration_ms"),
                        metadata=metadata_builder(left_item),
                    ),
                    "right": None,
                }
            )
            left_index += 1
            continue

        assert left_item is not None and right_item is not None
        left_label = str(left_item.get(label_key) or "unknown")
        right_label = str(right_item.get(label_key) or "unknown")
        left_step = left_item.get(step_key)
        right_step = right_item.get(step_key)

        match = False
        if left_step and right_step and left_step == right_step:
            match = True
        elif _normalize_label(left_label) == _normalize_label(right_label):
            match = True
        elif left_index + 1 < len(left_items) and _normalize_label(str(left_items[left_index + 1].get(label_key) or "")) == _normalize_label(right_label):
            pairs.append(
                {
                    "relation": "left_only",
                    "kind": kind,
                    "summary": _pair_summary(kind, "left_only", left_label, None),
                    "left": _target(
                        label=left_label,
                        status=left_item.get(status_key),
                        summary=next((left_item.get(key) for key in summary_keys if left_item.get(key)), None),
                        event_ids=list(left_item.get("event_ids", [left_item.get("event_id")]).copy()),
                        step_id=left_item.get(step_key),
                        duration_ms=left_item.get("duration_ms"),
                        metadata=metadata_builder(left_item),
                    ),
                    "right": None,
                }
            )
            left_index += 1
            continue
        elif right_index + 1 < len(right_items) and _normalize_label(left_label) == _normalize_label(str(right_items[right_index + 1].get(label_key) or "")):
            pairs.append(
                {
                    "relation": "right_only",
                    "kind": kind,
                    "summary": _pair_summary(kind, "right_only", None, right_label),
                    "left": None,
                    "right": _target(
                        label=right_label,
                        status=right_item.get(status_key),
                        summary=next((right_item.get(key) for key in summary_keys if right_item.get(key)), None),
                        event_ids=list(right_item.get("event_ids", [right_item.get("event_id")]).copy()),
                        step_id=right_item.get(step_key),
                        duration_ms=right_item.get("duration_ms"),
                        metadata=metadata_builder(right_item),
                    ),
                }
            )
            right_index += 1
            continue

        relation = "shared"
        if not match or left_item.get(status_key) != right_item.get(status_key):
            relation = "different"

        pairs.append(
            {
                "relation": relation,
                "kind": kind,
                "summary": _pair_summary(kind, relation, left_label, right_label),
                "left": _target(
                    label=left_label,
                    status=left_item.get(status_key),
                    summary=next((left_item.get(key) for key in summary_keys if left_item.get(key)), None),
                    event_ids=list(left_item.get("event_ids", [left_item.get("event_id")]).copy()),
                    step_id=left_item.get(step_key),
                    duration_ms=left_item.get("duration_ms"),
                    metadata=metadata_builder(left_item),
                ),
                "right": _target(
                    label=right_label,
                    status=right_item.get(status_key),
                    summary=next((right_item.get(key) for key in summary_keys if right_item.get(key)), None),
                    event_ids=list(right_item.get("event_ids", [right_item.get("event_id")]).copy()),
                    step_id=right_item.get(step_key),
                    duration_ms=right_item.get("duration_ms"),
                    metadata=metadata_builder(right_item),
                ),
            }
        )
        left_index += 1
        right_index += 1

    return pairs


def _final_file_state(file_activity: list[dict[str, Any]], patch_activity: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for item in file_activity:
        if item["event_type"] != "file.written":
            continue
        state[item["path"]] = {
            **item,
            "source": "file",
        }
    for item in patch_activity:
        state[item["path"]] = {
            "step_id": item["step_id"],
            "event_id": item["event_id"],
            "path": item["path"],
            "status": item["status"],
            "change_type": "update",
            "summary": item["summary"],
            "content_hash": item.get("after_hash"),
            "before_hash": item.get("before_hash"),
            "after_hash": item.get("after_hash"),
            "diff_summary": item.get("diff_summary"),
            "line_additions": item.get("line_additions"),
            "line_deletions": item.get("line_deletions"),
            "timestamp": item["timestamp"],
            "source": "patch",
        }
    return state


def _compare_file_state(left_state: dict[str, dict[str, Any]], right_state: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    paths = sorted(set(left_state) | set(right_state))
    for path in paths:
        left_item = left_state.get(path)
        right_item = right_state.get(path)
        relation = "shared"
        if left_item is None:
            relation = "right_only"
        elif right_item is None:
            relation = "left_only"
        elif (left_item.get("after_hash") or left_item.get("content_hash")) != (right_item.get("after_hash") or right_item.get("content_hash")):
            relation = "different"

        pairs.append(
            {
                "relation": relation,
                "kind": "file",
                "summary": _pair_summary("file", relation, path if left_item else None, path if right_item else None),
                "left": None
                if left_item is None
                else _target(
                    label=path,
                    status=left_item.get("status"),
                    summary=left_item.get("diff_summary") or left_item.get("summary"),
                    event_ids=[left_item.get("event_id")],
                    step_id=left_item.get("step_id"),
                    metadata={
                        "path": path,
                        "change_type": left_item.get("change_type"),
                        "after_hash": left_item.get("after_hash"),
                        "before_hash": left_item.get("before_hash"),
                        "line_additions": left_item.get("line_additions"),
                        "line_deletions": left_item.get("line_deletions"),
                        "source": left_item.get("source"),
                    },
                ),
                "right": None
                if right_item is None
                else _target(
                    label=path,
                    status=right_item.get("status"),
                    summary=right_item.get("diff_summary") or right_item.get("summary"),
                    event_ids=[right_item.get("event_id")],
                    step_id=right_item.get("step_id"),
                    metadata={
                        "path": path,
                        "change_type": right_item.get("change_type"),
                        "after_hash": right_item.get("after_hash"),
                        "before_hash": right_item.get("before_hash"),
                        "line_additions": right_item.get("line_additions"),
                        "line_deletions": right_item.get("line_deletions"),
                        "source": right_item.get("source"),
                    },
                ),
            }
        )
    return pairs


def _compare_artifacts(left_artifacts: list[Artifact], right_artifacts: list[Artifact]) -> list[dict[str, Any]]:
    left_map = {f"{artifact.kind}:{artifact.label}": artifact for artifact in left_artifacts}
    right_map = {f"{artifact.kind}:{artifact.label}": artifact for artifact in right_artifacts}
    pairs: list[dict[str, Any]] = []
    for key in sorted(set(left_map) | set(right_map)):
        left_artifact = left_map.get(key)
        right_artifact = right_map.get(key)
        relation = "shared"
        if left_artifact is None:
            relation = "right_only"
        elif right_artifact is None:
            relation = "left_only"
        elif left_artifact.content_hash != right_artifact.content_hash:
            relation = "different"

        label = key.split(":", 1)[1]
        pairs.append(
            {
                "relation": relation,
                "kind": "artifact",
                "summary": _pair_summary("artifact", relation, label if left_artifact else None, label if right_artifact else None),
                "left": None
                if left_artifact is None
                else _target(
                    label=left_artifact.label,
                    status="created",
                    summary=left_artifact.summary,
                    event_ids=[left_artifact.source_event_id] if left_artifact.source_event_id else [],
                    step_id=None,
                    metadata={"kind": left_artifact.kind, "content_hash": left_artifact.content_hash},
                ),
                "right": None
                if right_artifact is None
                else _target(
                    label=right_artifact.label,
                    status="created",
                    summary=right_artifact.summary,
                    event_ids=[right_artifact.source_event_id] if right_artifact.source_event_id else [],
                    step_id=None,
                    metadata={"kind": right_artifact.kind, "content_hash": right_artifact.content_hash},
                ),
            }
        )
    return pairs


def _timeline_sequence(
    tool_chain: list[dict[str, Any]],
    command_chain: list[dict[str, Any]],
    file_activity: list[dict[str, Any]],
    patch_activity: list[dict[str, Any]],
    lookup: dict[int, Event],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in tool_chain:
        items.append(
            {
                "kind": "tool",
                "label": item["tool_name"],
                "status": item["status"],
                "summary": item["error_summary"] or item["output_summary"] or item["args_summary"],
                "event_ids": item["event_ids"],
                "step_id": item["step_id"],
                "duration_ms": item["duration_ms"],
                "metadata": {"tool_name": item["tool_name"]},
                "_seq": _first_seq(item["event_ids"], lookup),
            }
        )
    for item in command_chain:
        items.append(
            {
                "kind": "command",
                "label": item["command"],
                "status": item["status"],
                "summary": item["error_summary"] or item["output_summary"],
                "event_ids": item["event_ids"],
                "step_id": item["step_id"],
                "duration_ms": item["duration_ms"],
                "metadata": {"cwd": item["cwd"], "exit_code": item["exit_code"]},
                "_seq": _first_seq(item["event_ids"], lookup),
            }
        )
    for item in file_activity:
        items.append(
            {
                "kind": "file",
                "label": item["path"],
                "status": item["status"],
                "summary": item["summary"],
                "event_ids": [item["event_id"]],
                "step_id": item["step_id"],
                "duration_ms": None,
                "metadata": {"event_type": item["event_type"], "change_type": item["change_type"]},
                "_seq": lookup[item["event_id"]].seq,
            }
        )
    for item in patch_activity:
        items.append(
            {
                "kind": "file",
                "label": item["path"],
                "status": item["status"],
                "summary": item["summary"],
                "event_ids": [item["event_id"]],
                "step_id": item["step_id"],
                "duration_ms": None,
                "metadata": {"event_type": "patch.applied", "change_type": "update"},
                "_seq": lookup[item["event_id"]].seq,
            }
        )
    items.sort(key=lambda item: item["_seq"])
    return items


def _align_timeline(left_items: list[dict[str, Any]], right_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    left_index = 0
    right_index = 0

    while left_index < len(left_items) or right_index < len(right_items):
        left_item = left_items[left_index] if left_index < len(left_items) else None
        right_item = right_items[right_index] if right_index < len(right_items) else None

        if left_item is None and right_item is not None:
            pairs.append(
                {
                    "relation": "right_only",
                    "kind": right_item["kind"],
                    "summary": f"Only right run has {right_item['kind']}: {right_item['label']}.",
                    "left": None,
                    "right": _target(
                        label=right_item["label"],
                        status=right_item["status"],
                        summary=right_item["summary"],
                        event_ids=right_item["event_ids"],
                        step_id=right_item["step_id"],
                        duration_ms=right_item["duration_ms"],
                        metadata=right_item["metadata"],
                    ),
                }
            )
            right_index += 1
            continue

        if right_item is None and left_item is not None:
            pairs.append(
                {
                    "relation": "left_only",
                    "kind": left_item["kind"],
                    "summary": f"Only left run has {left_item['kind']}: {left_item['label']}.",
                    "left": _target(
                        label=left_item["label"],
                        status=left_item["status"],
                        summary=left_item["summary"],
                        event_ids=left_item["event_ids"],
                        step_id=left_item["step_id"],
                        duration_ms=left_item["duration_ms"],
                        metadata=left_item["metadata"],
                    ),
                    "right": None,
                }
            )
            left_index += 1
            continue

        assert left_item is not None and right_item is not None
        if left_item["kind"] == right_item["kind"] and _normalize_label(left_item["label"]) == _normalize_label(right_item["label"]):
            relation = "shared" if left_item["status"] == right_item["status"] else "different"
            pairs.append(
                {
                    "relation": relation,
                    "kind": left_item["kind"],
                    "summary": _pair_summary(left_item["kind"], relation, left_item["label"], right_item["label"]),
                    "left": _target(
                        label=left_item["label"],
                        status=left_item["status"],
                        summary=left_item["summary"],
                        event_ids=left_item["event_ids"],
                        step_id=left_item["step_id"],
                        duration_ms=left_item["duration_ms"],
                        metadata=left_item["metadata"],
                    ),
                    "right": _target(
                        label=right_item["label"],
                        status=right_item["status"],
                        summary=right_item["summary"],
                        event_ids=right_item["event_ids"],
                        step_id=right_item["step_id"],
                        duration_ms=right_item["duration_ms"],
                        metadata=right_item["metadata"],
                    ),
                }
            )
            left_index += 1
            right_index += 1
            continue

        if left_item["_seq"] <= right_item["_seq"]:
            pairs.append(
                {
                    "relation": "left_only",
                    "kind": left_item["kind"],
                    "summary": f"Only left run has {left_item['kind']}: {left_item['label']}.",
                    "left": _target(
                        label=left_item["label"],
                        status=left_item["status"],
                        summary=left_item["summary"],
                        event_ids=left_item["event_ids"],
                        step_id=left_item["step_id"],
                        duration_ms=left_item["duration_ms"],
                        metadata=left_item["metadata"],
                    ),
                    "right": None,
                }
            )
            left_index += 1
        else:
            pairs.append(
                {
                    "relation": "right_only",
                    "kind": right_item["kind"],
                    "summary": f"Only right run has {right_item['kind']}: {right_item['label']}.",
                    "left": None,
                    "right": _target(
                        label=right_item["label"],
                        status=right_item["status"],
                        summary=right_item["summary"],
                        event_ids=right_item["event_ids"],
                        step_id=right_item["step_id"],
                        duration_ms=right_item["duration_ms"],
                        metadata=right_item["metadata"],
                    ),
                }
            )
            right_index += 1

    return pairs


def _overview_diff(left_run: Run, right_run: Run, left_events: list[Event], right_events: list[Event]) -> dict[str, Any]:
    left_token_total = sum(int((event.event_metadata.get("usage") or {}).get("total_tokens") or 0) for event in left_events if event.type == "model.responded")
    right_token_total = sum(int((event.event_metadata.get("usage") or {}).get("total_tokens") or 0) for event in right_events if event.type == "model.responded")

    duration_ms_delta = None
    if left_run.ended_at is not None and right_run.ended_at is not None:
        left_duration = int((left_run.ended_at - left_run.started_at).total_seconds() * 1000)
        right_duration = int((right_run.ended_at - right_run.started_at).total_seconds() * 1000)
        duration_ms_delta = right_duration - left_duration

    return {
        "tool_count_delta": right_run.tool_count - left_run.tool_count,
        "command_count_delta": sum(1 for event in right_events if event.type in {"command.succeeded", "command.failed"})
        - sum(1 for event in left_events if event.type in {"command.succeeded", "command.failed"}),
        "error_count_delta": right_run.error_count - left_run.error_count,
        "retry_count_delta": right_run.retry_count - left_run.retry_count,
        "artifact_count_delta": right_run.artifact_count - left_run.artifact_count,
        "token_total_delta": right_token_total - left_token_total,
        "duration_ms_delta": duration_ms_delta,
    }


def _detect_retry_without_adaptation(tool_chain: list[dict[str, Any]]) -> list[int]:
    last_failed_by_tool: dict[str, dict[str, Any]] = {}
    for item in tool_chain:
        if item["status"] == "failed":
            last_failed_by_tool[item["tool_name"]] = item
            continue
        previous = last_failed_by_tool.get(item["tool_name"])
        if previous and previous.get("args_summary") == item.get("args_summary"):
            return previous["event_ids"] + item["event_ids"]
    return []


def _derive_root_cause(
    *,
    left_run: Run,
    right_run: Run,
    divergence: dict[str, Any] | None,
    tool_diff: list[dict[str, Any]],
    file_diff: list[dict[str, Any]],
    artifact_diff: list[dict[str, Any]],
    left_tool_chain: list[dict[str, Any]],
    right_tool_chain: list[dict[str, Any]],
    left_lookup: dict[int, Event],
    right_lookup: dict[int, Event],
) -> dict[str, Any]:
    if divergence is None:
        return {
            "label": "no_observable_root_cause",
            "summary": "No observable divergence was found between the selected runs.",
            "first_causal_event_left": None,
            "first_causal_event_right": None,
            "supporting_event_ids": {"left": [], "right": []},
            "impact_summary": "Both runs stayed aligned across the observed execution path.",
            "confidence": "low",
        }

    left_event_ids = divergence.get("left_event_ids", [])
    right_event_ids = divergence.get("right_event_ids", [])
    mismatch_kind = divergence["first_mismatch_kind"]

    left_events = [left_lookup[event_id] for event_id in left_event_ids if event_id in left_lookup]
    right_events = [right_lookup[event_id] for event_id in right_event_ids if event_id in right_lookup]

    if any(event.type == "run.failed" and event.error_code == "provider_error" for event in left_events + right_events):
        return {
            "label": "provider_failure",
            "summary": "The provider failed before the runs could stay aligned.",
            "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
            "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
            "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
            "impact_summary": "The provider error interrupted the execution path and changed the final status.",
            "confidence": "high",
        }

    if mismatch_kind == "command":
        return {
            "label": "command_failure",
            "summary": "A command diverged first, and one run failed or changed outcome at that command step.",
            "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
            "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
            "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
            "impact_summary": f"Run status diverged to {left_run.status} vs {right_run.status} after command execution changed.",
            "confidence": "high",
        }

    if mismatch_kind == "tool":
        retry_left = _detect_retry_without_adaptation(left_tool_chain)
        retry_right = _detect_retry_without_adaptation(right_tool_chain)
        if retry_left or retry_right:
            return {
                "label": "retry_without_adaptation",
                "summary": "One run retried the same tool without changing the observable input or path.",
                "first_causal_event_left": (retry_left or left_event_ids or [None])[0],
                "first_causal_event_right": (retry_right or right_event_ids or [None])[0],
                "supporting_event_ids": {"left": retry_left or left_event_ids, "right": retry_right or right_event_ids},
                "impact_summary": "The extra retry delayed or derailed the run without introducing a new strategy.",
                "confidence": "high",
            }

        first_tool_diff = next((item for item in tool_diff if item["relation"] == "different"), None)
        if first_tool_diff and first_tool_diff.get("left") and first_tool_diff.get("right"):
            left_label = first_tool_diff["left"]["label"]
            right_label = first_tool_diff["right"]["label"]
            if left_label != right_label:
                return {
                    "label": "bad_tool_selection",
                    "summary": "The runs chose different tools at the same point in the execution.",
                    "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
                    "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
                    "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
                    "impact_summary": f"The tool choice changed the rest of the execution path: {left_label} vs {right_label}.",
                    "confidence": "high",
                }

        return {
            "label": "dead_end_branch",
            "summary": "The runs diverged on tool execution and one branch stopped matching the successful path.",
            "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
            "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
            "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
            "impact_summary": "The tool path changed before the final result diverged.",
            "confidence": "medium",
        }

    different_file = next((item for item in file_diff if item["relation"] == "different"), None)
    if mismatch_kind == "file" or different_file is not None:
        if different_file is None and (
            not any(item["relation"] in {"left_only", "right_only"} for item in file_diff)
            and (
            any(event.type == "file.read" for event in left_events) or any(event.type == "file.read" for event in right_events)
            )
        ):
            return {
                "label": "missing_context",
                "summary": "One run observed file context that the other run did not capture before diverging.",
                "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
                "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
                "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
                "impact_summary": "The missing file read changed the context available to the run before the result diverged.",
                "confidence": "medium",
            }
        return {
            "label": "file_change_divergence",
            "summary": "The runs produced different file changes or patched different content.",
            "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
            "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
            "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
            "impact_summary": "The file state diverged before the final output or artifact changed.",
            "confidence": "high",
        }

    different_artifact = next((item for item in artifact_diff if item["relation"] == "different"), None)
    if different_artifact is not None:
        return {
            "label": "artifact_mismatch",
            "summary": "The runs ended with different persisted artifacts despite sharing part of the execution path.",
            "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
            "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
            "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
            "impact_summary": "The observable output differed at the artifact layer.",
            "confidence": "medium",
        }

    return {
        "label": "no_observable_root_cause",
        "summary": "The runs diverged, but the first causal reason is not observable from the stored events.",
        "first_causal_event_left": left_event_ids[0] if left_event_ids else None,
        "first_causal_event_right": right_event_ids[0] if right_event_ids else None,
        "supporting_event_ids": {"left": left_event_ids, "right": right_event_ids},
        "impact_summary": "The result changed after an observable divergence, but not enough evidence was captured to classify it.",
        "confidence": "low",
    }


def _first_divergence(pairs: list[dict[str, Any]], left_lookup: dict[int, Event], right_lookup: dict[int, Event]) -> dict[str, Any] | None:
    candidates = [pair for pair in pairs if pair["relation"] != "shared"]
    if not candidates:
        return None

    def sort_key(pair: dict[str, Any]) -> int:
        seqs: list[int] = []
        if pair.get("left"):
            seqs.append(_first_seq(pair["left"]["event_ids"], left_lookup))
        if pair.get("right"):
            seqs.append(_first_seq(pair["right"]["event_ids"], right_lookup))
        return min(seqs) if seqs else 10**9

    first_pair = min(candidates, key=sort_key)
    return {
        "first_mismatch_kind": first_pair["kind"],
        "left_event_ids": first_pair["left"]["event_ids"] if first_pair.get("left") else [],
        "right_event_ids": first_pair["right"]["event_ids"] if first_pair.get("right") else [],
        "summary": first_pair["summary"],
    }


def compare_runs(
    *,
    left_run: Run,
    right_run: Run,
    left_events: list[Event],
    right_events: list[Event],
    left_artifacts: list[Artifact],
    right_artifacts: list[Artifact],
    left_decisions: list[Decision],
    right_decisions: list[Decision],
) -> dict[str, Any]:
    left_lookup = _event_map(left_events)
    right_lookup = _event_map(right_events)

    left_tool_chain = build_tool_chain(left_events)
    right_tool_chain = build_tool_chain(right_events)
    left_command_chain = build_command_chain(left_events)
    right_command_chain = build_command_chain(right_events)
    left_file_activity = build_file_activity(left_events)
    right_file_activity = build_file_activity(right_events)
    left_patch_activity = build_patch_activity(left_events)
    right_patch_activity = build_patch_activity(right_events)

    tool_diff = _align_sequence(
        left_tool_chain,
        right_tool_chain,
        kind="tool",
        label_key="tool_name",
        summary_keys=("error_summary", "output_summary", "args_summary"),
        metadata_builder=lambda item: {
            "tool_name": item.get("tool_name"),
            "error_code": item.get("error_code"),
            "artifact_count": item.get("artifact_count"),
        },
    )
    command_diff = _align_sequence(
        left_command_chain,
        right_command_chain,
        kind="command",
        label_key="command",
        summary_keys=("error_summary", "output_summary"),
        metadata_builder=lambda item: {
            "cwd": item.get("cwd"),
            "exit_code": item.get("exit_code"),
            "error_code": item.get("error_code"),
        },
    )
    decision_diff = _align_sequence(
        [
            {
                "step_id": decision.id,
                "label": decision.label,
                "status": decision.outcome,
                "summary": decision.rationale_summary,
                "event_ids": decision.evidence_event_ids,
                "duration_ms": None,
                "kind": decision.kind,
            }
            for decision in left_decisions
        ],
        [
            {
                "step_id": decision.id,
                "label": decision.label,
                "status": decision.outcome,
                "summary": decision.rationale_summary,
                "event_ids": decision.evidence_event_ids,
                "duration_ms": None,
                "kind": decision.kind,
            }
            for decision in right_decisions
        ],
        kind="decision",
        label_key="label",
        summary_keys=("summary",),
        metadata_builder=lambda item: {"kind": item.get("kind")},
    )

    file_diff = _compare_file_state(
        _final_file_state(left_file_activity, left_patch_activity),
        _final_file_state(right_file_activity, right_patch_activity),
    )
    artifact_diff = _compare_artifacts(left_artifacts, right_artifacts)

    aligned_timeline = _align_timeline(
        _timeline_sequence(left_tool_chain, left_command_chain, left_file_activity, left_patch_activity, left_lookup),
        _timeline_sequence(right_tool_chain, right_command_chain, right_file_activity, right_patch_activity, right_lookup),
    )
    divergence = _first_divergence(aligned_timeline, left_lookup, right_lookup)
    root_cause = _derive_root_cause(
        left_run=left_run,
        right_run=right_run,
        divergence=divergence,
        tool_diff=tool_diff,
        file_diff=file_diff,
        artifact_diff=artifact_diff,
        left_tool_chain=left_tool_chain,
        right_tool_chain=right_tool_chain,
        left_lookup=left_lookup,
        right_lookup=right_lookup,
    )

    return {
        "overview_diff": _overview_diff(left_run, right_run, left_events, right_events),
        "divergence": divergence,
        "aligned_timeline": aligned_timeline,
        "tool_diff": tool_diff,
        "command_diff": command_diff,
        "file_diff": file_diff,
        "artifact_diff": artifact_diff,
        "decision_diff": decision_diff,
        "root_cause": root_cause,
        "left_timeline_groups": build_timeline_groups(left_events),
        "right_timeline_groups": build_timeline_groups(right_events),
    }
