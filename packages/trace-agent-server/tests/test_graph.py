from __future__ import annotations

from trace_agent_server.models import Artifact, Event
from trace_agent_server.services.graph import build_execution_graph


def event(event_id: int, event_type: str, step_id: str | None, *, status: str | None = None, tool_name: str | None = None,
          summary: str = "", metadata: dict | None = None, duration_ms: int | None = None) -> Event:
    return Event(id=event_id, run_id="r", seq=event_id, actor="sdk", type=event_type, summary=summary, status=status,
                 step_id=step_id, tool_name=tool_name, event_metadata=metadata or {}, duration_ms=duration_ms)


class TestExecutionGraphSteps:
    def test_a_tool_is_one_node_with_its_result_not_a_started_and_a_finished_node(self) -> None:
        events = [
            event(1, "run.started", None),
            event(2, "tool.started", "t1", tool_name="search", status="completed"),
            event(3, "tool.succeeded", "t1", tool_name="search", status="succeeded", summary="3 results", duration_ms=40),
            event(4, "run.completed", None),
        ]

        graph = build_execution_graph(events, [])

        assert [n["data"]["eventId"] for n in graph["nodes"]] == [1, 3, 4]
        tool = graph["nodes"][1]
        assert (tool["label"], tool["data"]["summary"], tool["data"]["durationMs"], tool["data"]["toolName"]) == ("tool.succeeded", "3 results", 40, "search")
        assert tool["data"]["evidenceIds"] == [2, 3]
        assert tool["data"]["stepKind"] == "tool"

    def test_the_nodes_are_chained_in_the_order_the_steps_began(self) -> None:
        events = [event(1, "llm.started", "l1"), event(2, "tool.started", "t1"), event(3, "llm.completed", "l1"), event(4, "tool.succeeded", "t1")]

        graph = build_execution_graph(events, [])

        assert [n["data"]["eventId"] for n in graph["nodes"]] == [3, 4]  # each node is named after the last event of its step
        assert [(e["source"], e["target"]) for e in graph["edges"]] == [("event-3", "event-4")]

    def test_a_step_that_failed_at_any_point_is_failed_and_its_edge_animated(self) -> None:
        events = [event(1, "tool.started", "t1", status="completed"), event(2, "tool.failed", "t1", status="failed"), event(3, "tool.started", "t2")]

        graph = build_execution_graph(events, [])

        assert graph["nodes"][0]["data"]["status"] == "failed"
        assert graph["edges"][0]["animated"] is False  # the edge into the next step follows that step, which did not fail

    def test_the_command_of_a_command_step_is_kept_for_its_title(self) -> None:
        events = [event(1, "command.started", "c1", metadata={"command": "python -c # Leer\nprint(1)"}), event(2, "command.succeeded", "c1", metadata={"command": "python -c # Leer\nprint(1)"})]

        graph = build_execution_graph(events, [])

        assert graph["nodes"][0]["data"]["command"] == "python -c # Leer\nprint(1)"
        assert graph["nodes"][0]["data"]["stepKind"] == "command"

    def test_an_artifact_hangs_from_the_node_of_the_step_that_made_it(self) -> None:
        events = [event(1, "tool.started", "t1"), event(2, "tool.succeeded", "t1")]
        artifact = Artifact(id=9, run_id="r", kind="file", label="report", summary="the report", source_event_id=1)

        graph = build_execution_graph(events, [artifact])

        assert ("event-2", "artifact-9") in [(e["source"], e["target"]) for e in graph["edges"]]
