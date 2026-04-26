from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from visor_agentico.config import Settings
from visor_agentico.models import Event, Run
from visor_agentico.services.run_summary import build_tool_chain


TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "have",
    "need",
    "plan",
    "build",
    "using",
    "use",
    "agent",
    "tool",
    "tools",
}


def _goal_tokens(goal: str) -> set[str]:
    tokens = {token.lower() for token in TOKEN_PATTERN.findall(goal)}
    return {token for token in tokens if len(token) > 2 and token not in STOP_WORDS}


def _duration_ms(run: Run) -> int | None:
    if run.ended_at is None:
        return None
    return max(0, int((run.ended_at - run.started_at).total_seconds() * 1000))


def _extract_usage(event: Event) -> dict[str, int]:
    usage = event.event_metadata.get("usage", {})
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


def _pricing_key(provider: str | None, model: str | None) -> list[str]:
    keys: list[str] = []
    if provider and model:
        keys.append(f"{provider}:{model}")
    if model:
        keys.append(model)
    return keys


def build_tool_graph(tool_chain: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    step_to_node: dict[str, str] = {}

    for index, item in enumerate(tool_chain):
        node_id = f"tool-chain-{item['step_id']}"
        step_to_node[item["step_id"]] = node_id
        nodes.append(
            {
                "id": node_id,
                "type": "tool_chain",
                "label": item["tool_name"],
                "position": {"x": float(index * 220), "y": 80.0 if index % 2 == 0 else 180.0},
                "data": {
                    "status": item["status"],
                    "durationMs": item["duration_ms"],
                    "callId": item["call_id"],
                    "summary": item["error_summary"] or item["output_summary"] or item["args_summary"],
                    "evidenceIds": item["event_ids"],
                    "artifactCount": item["artifact_count"],
                },
            }
        )

    for index, item in enumerate(tool_chain):
        if index == 0:
            continue
        source_step = item["parent_step_id"] or tool_chain[index - 1]["step_id"]
        source_node = step_to_node.get(source_step)
        target_node = step_to_node[item["step_id"]]
        if source_node is None:
            source_node = step_to_node[tool_chain[index - 1]["step_id"]]
        edges.append(
            {
                "id": f"tool-chain-edge-{source_node}-{target_node}",
                "source": source_node,
                "target": target_node,
                "label": item["status"],
                "animated": item["status"] == "failed",
            }
        )
    return {"nodes": nodes, "edges": edges}


def build_tool_metrics(events: list[Event], tool_chain: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    attribution: dict[str, dict[str, int]] = defaultdict(lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    for index, event in enumerate(events):
        if event.type != "model.responded":
            continue
        tool_call_count = int(event.event_metadata.get("tool_call_count") or 0)
        if tool_call_count <= 0:
            continue

        requested_events: list[Event] = []
        cursor = index + 1
        while cursor < len(events) and events[cursor].type == "tool.requested":
            requested_events.append(events[cursor])
            cursor += 1
        if not requested_events:
            continue

        usage = _extract_usage(event)
        divisor = max(1, len(requested_events))
        # Split one model turn across the tool calls it produced.
        for requested_event in requested_events:
            key = requested_event.event_metadata.get("call_id") if isinstance(requested_event.event_metadata.get("call_id"), str) else requested_event.step_id
            if not key:
                continue
            attribution[key]["prompt_tokens"] += usage["prompt_tokens"] // divisor
            attribution[key]["completion_tokens"] += usage["completion_tokens"] // divisor
            attribution[key]["total_tokens"] += usage["total_tokens"] // divisor

    grouped: dict[str, dict[str, Any]] = {}
    for item in tool_chain:
        tool_name = item["tool_name"]
        metric = grouped.setdefault(
            tool_name,
            {
                "tool_name": tool_name,
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0,
                "max_duration_ms": 0,
                "artifact_count": 0,
                "attributed_prompt_tokens": 0,
                "attributed_completion_tokens": 0,
                "attributed_total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "providers": set(),
                "models": set(),
                "_cost_available": False,
            },
        )
        metric["call_count"] += 1
        if item["status"] == "succeeded":
            metric["success_count"] += 1
        if item["status"] == "failed":
            metric["failure_count"] += 1

        duration = int(item["duration_ms"] or 0)
        metric["total_duration_ms"] += duration
        metric["max_duration_ms"] = max(metric["max_duration_ms"], duration)
        metric["artifact_count"] += int(item["artifact_count"] or 0)
        if item["provider"]:
            metric["providers"].add(item["provider"])
        if item["model"]:
            metric["models"].add(item["model"])

        key = item["call_id"] or item["step_id"]
        usage = attribution.get(key, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        metric["attributed_prompt_tokens"] += usage["prompt_tokens"]
        metric["attributed_completion_tokens"] += usage["completion_tokens"]
        metric["attributed_total_tokens"] += usage["total_tokens"]

        pricing = None
        for pricing_key in _pricing_key(item["provider"], item["model"]):
            if pricing_key in settings.model_pricing:
                pricing = settings.model_pricing[pricing_key]
                break
        if pricing:
            prompt_rate = float(pricing.get("prompt_per_1k", 0.0))
            completion_rate = float(pricing.get("completion_per_1k", 0.0))
            metric["estimated_cost_usd"] += (
                usage["prompt_tokens"] / 1000.0 * prompt_rate
                + usage["completion_tokens"] / 1000.0 * completion_rate
            )
            metric["_cost_available"] = True

    results: list[dict[str, Any]] = []
    for metric in grouped.values():
        call_count = max(1, metric["call_count"])
        results.append(
            {
                "tool_name": metric["tool_name"],
                "call_count": metric["call_count"],
                "success_count": metric["success_count"],
                "failure_count": metric["failure_count"],
                "total_duration_ms": metric["total_duration_ms"],
                "avg_duration_ms": int(metric["total_duration_ms"] / call_count),
                "max_duration_ms": metric["max_duration_ms"],
                "artifact_count": metric["artifact_count"],
                "attributed_prompt_tokens": metric["attributed_prompt_tokens"],
                "attributed_completion_tokens": metric["attributed_completion_tokens"],
                "attributed_total_tokens": metric["attributed_total_tokens"],
                "estimated_cost_usd": round(metric["estimated_cost_usd"], 4) if metric["_cost_available"] else None,
                "providers": sorted(metric["providers"]),
                "models": sorted(metric["models"]),
            }
        )
    results.sort(key=lambda item: (-item["attributed_total_tokens"], -item["total_duration_ms"], item["tool_name"]))
    return results


def build_similar_runs(
    session: Session,
    run: Run,
    current_tool_chain: list[dict[str, Any]],
    *,
    limit: int = 5,
    same_agent_only: bool = False,
    status_filter: str | None = None,
    shared_tools_only: bool = False,
    min_score: float = 0.15,
) -> list[dict[str, Any]]:
    candidates = list(
        session.scalars(
            select(Run)
            .where(Run.id != run.id)
            .order_by(Run.started_at.desc())
            .limit(40)
        )
    )
    current_goal_tokens = _goal_tokens(run.goal)
    current_tools = {item["tool_name"] for item in current_tool_chain}
    current_scenario = run.run_metadata.get("scenario")
    results: list[dict[str, Any]] = []

    for candidate in candidates:
        if same_agent_only and candidate.agent_name != run.agent_name:
            continue
        if status_filter and candidate.status != status_filter:
            continue

        candidate_events = list(session.scalars(select(Event).where(Event.run_id == candidate.id).order_by(Event.seq)))
        candidate_tool_chain = build_tool_chain(candidate_events)
        candidate_tools = {item["tool_name"] for item in candidate_tool_chain}
        candidate_goal_tokens = _goal_tokens(candidate.goal)

        goal_union = current_goal_tokens | candidate_goal_tokens
        tool_union = current_tools | candidate_tools
        goal_similarity = len(current_goal_tokens & candidate_goal_tokens) / len(goal_union) if goal_union else 0.0
        tool_similarity = len(current_tools & candidate_tools) / len(tool_union) if tool_union else 0.0
        score = 0.45 * goal_similarity + 0.2 * tool_similarity

        reason_parts: list[str] = []
        if candidate.agent_name == run.agent_name:
            score += 0.2
            reason_parts.append("same agent")
        if current_scenario and candidate.run_metadata.get("scenario") == current_scenario:
            score += 0.15
            reason_parts.append("same scenario")
        shared_tools = sorted(current_tools & candidate_tools)
        if shared_tools_only and not shared_tools:
            continue
        if shared_tools:
            reason_parts.append(f"shared tools: {', '.join(shared_tools[:3])}")
        if goal_similarity > 0:
            reason_parts.append("goal overlap")

        # Keep the score simple and explainable: goal overlap, shared tools and same execution context.
        if score < min_score:
            continue

        results.append(
            {
                "run_id": candidate.id,
                "agent_name": candidate.agent_name,
                "goal": candidate.goal,
                "status": candidate.status,
                "started_at": candidate.started_at,
                "ended_at": candidate.ended_at,
                "duration_ms": _duration_ms(candidate),
                "tool_count": candidate.tool_count,
                "error_count": candidate.error_count,
                "retry_count": candidate.retry_count,
                "provider": candidate.provider,
                "model": candidate.model,
                "similarity_score": round(min(score, 1.0), 3),
                "shared_tools": shared_tools,
                "reason": ", ".join(reason_parts) if reason_parts else "similar recent run",
            }
        )

    results.sort(key=lambda item: (item["similarity_score"], item["started_at"]), reverse=True)
    return results[:limit]
