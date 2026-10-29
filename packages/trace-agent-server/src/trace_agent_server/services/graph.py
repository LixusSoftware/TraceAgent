from __future__ import annotations

from typing import Any

from trace_agent_server.models import Artifact, Decision, Event


def _steps(events: list[Event]) -> list[list[Event]]:
    """Events grouped by the step they belong to (a tool call's start and end, a model call's request and
    response), in the order the steps began. An event without a step is a step of its own."""
    steps: list[list[Event]] = []
    position: dict[str, int] = {}
    for event in events:
        if event.step_id and event.step_id in position:
            steps[position[event.step_id]].append(event)
            continue
        if event.step_id:
            position[event.step_id] = len(steps)
        steps.append([event])
    return steps


def build_execution_graph(events: list[Event], artifacts: list[Artifact]) -> dict[str, Any]:
    """One node per step, not per event: a tool is one node with its result, not a 'started' and a 'finished'."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_of_event: dict[int, str] = {}
    x = 0.0
    y = 0.0

    steps = _steps(events)
    for index, step in enumerate(steps):
        last = step[-1]
        node_id = f"event-{last.id}"
        for event in step:
            node_of_event[event.id] = node_id
        failed = any(event.status == "failed" for event in step)
        command = next((e.event_metadata.get("command") for e in step if e.type.startswith("command.") and e.event_metadata), None)
        nodes.append(
            {
                "id": node_id,
                "type": "event",
                "label": last.type,
                "position": {"x": x, "y": y},
                "data": {
                    "summary": last.summary,
                    # The last event of the step (its result) is the one the inspector opens.
                    "eventId": last.id,
                    "toolName": last.tool_name,
                    "status": "failed" if failed else last.status,
                    "durationMs": last.duration_ms,
                    "stepKind": step[0].type.split(".")[0],
                    "command": command,
                    "evidenceIds": [event.id for event in step],
                },
            }
        )
        if index > 0:
            previous = nodes[index - 1]
            edges.append(
                {
                    "id": f"edge-{previous['id']}-{node_id}",
                    "source": previous["id"],
                    "target": node_id,
                    "label": None,
                    "animated": failed or last.type == "run.failed",
                }
            )
        x += 220
        if (index + 1) % 4 == 0:
            x = 0.0
            y += 170

    artifact_y = y + 200
    for index, artifact in enumerate(artifacts):
        nodes.append(
            {
                "id": f"artifact-{artifact.id}",
                "type": "artifact",
                "label": artifact.label,
                "position": {"x": float(index * 220), "y": artifact_y},
                "data": {
                    "summary": artifact.summary,
                    "artifactId": artifact.id,
                    "kind": artifact.kind,
                    "evidenceIds": [artifact.source_event_id] if artifact.source_event_id else [],
                },
            }
        )
        if artifact.source_event_id:
            edges.append(
                {
                    "id": f"edge-artifact-{artifact.id}",
                    "source": node_of_event.get(artifact.source_event_id, f"event-{artifact.source_event_id}"),
                    "target": f"artifact-{artifact.id}",
                    "label": "artifact",
                    "animated": False,
                }
            )
    return {"nodes": nodes, "edges": edges}


def build_decision_graph(decisions: list[Decision]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        nodes.append(
            {
                "id": f"decision-{decision.id}",
                "type": "decision",
                "label": decision.label,
                "position": {"x": float(index * 240), "y": 60.0 if index % 2 == 0 else 180.0},
                "data": {
                    "kind": decision.kind,
                    "summary": decision.rationale_summary,
                    "decisionId": decision.id,
                    "evidenceIds": decision.evidence_event_ids,
                    "outcome": decision.outcome,
                },
            }
        )
        if index > 0:
            edges.append(
                {
                    "id": f"edge-decision-{decisions[index - 1].id}-{decision.id}",
                    "source": f"decision-{decisions[index - 1].id}",
                    "target": f"decision-{decision.id}",
                    "label": decision.kind,
                    "animated": decision.kind in {"retry", "recovery"},
                }
            )
    return {"nodes": nodes, "edges": edges}
