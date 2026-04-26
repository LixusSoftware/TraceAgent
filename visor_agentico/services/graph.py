from __future__ import annotations

from typing import Any

from visor_agentico.models import Artifact, Decision, Event


def build_execution_graph(events: list[Event], artifacts: list[Artifact]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    x = 0.0
    y = 0.0

    for index, event in enumerate(events):
        nodes.append(
            {
                "id": f"event-{event.id}",
                "type": "event",
                "label": event.type,
                "position": {"x": x, "y": y},
                "data": {
                    "summary": event.summary,
                    "eventId": event.id,
                    "toolName": event.tool_name,
                    "status": event.status,
                    "evidenceIds": [event.id],
                },
            }
        )
        if index > 0:
            edges.append(
                {
                    "id": f"edge-event-{events[index - 1].id}-{event.id}",
                    "source": f"event-{events[index - 1].id}",
                    "target": f"event-{event.id}",
                    "label": None,
                    "animated": event.type in {"tool.failed", "run.failed"},
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
                    "source": f"event-{artifact.source_event_id}",
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
