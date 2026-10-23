import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Timeline } from "./Timeline";
import type { EventItem, TimelineGroup, TimelineResponse } from "../../types";

function makeEvent(seq: number, type: string, summary: string, stepId: string | null, parent: string | null): EventItem {
  return {
    id: seq,
    seq,
    timestamp: "2026-10-23T06:00:00",
    step_id: stepId,
    parent_step_id: parent,
    actor: "sdk",
    type,
    summary,
    status: "succeeded",
    duration_ms: null,
    provider: null,
    model: null,
    tool_name: null,
    artifact_refs: [],
    error_code: null,
    payload_hash: null,
    payload_full: null,
    metadata: {},
  };
}

function makeGroup(stepId: string, label: string, parent: string | null, events: EventItem[]): TimelineGroup {
  return {
    step_id: stepId,
    label,
    status: "succeeded",
    step_type: "run",
    tool_name: null,
    call_id: null,
    parent_step_id: parent,
    event_count: events.length,
    started_at: "2026-10-23T06:00:00",
    ended_at: "2026-10-23T06:00:01",
    duration_ms: 10,
    events,
  };
}

function renderTimeline(groups: TimelineGroup[]) {
  const timeline: TimelineResponse = { run_id: "run-1", groups };
  return render(<Timeline timeline={timeline} selectedEvent={null} onSelectEvent={() => {}} isLoading={false} />);
}

describe("Timeline", () => {
  const run = makeGroup("run-1", "chain.completed", null, [
    makeEvent(2, "chain.started", "Run started", "run-1", null),
    makeEvent(7, "chain.completed", "Run completed", "run-1", null),
  ])
  const llm = makeGroup("llm-1", "llm.completed", "run-1", [
    makeEvent(3, "llm.started", "LLM call started", "llm-1", "run-1"),
    makeEvent(4, "llm.completed", "LLM call completed", "llm-1", "run-1"),
  ])
  const tool = makeGroup("tool-1", "get_weather", "run-1", [
    makeEvent(5, "tool.started", "Started get_weather.", "tool-1", "run-1"),
    makeEvent(6, "tool.succeeded", "get_weather done", "tool-1", "run-1"),
  ])

  it("shows the event total including events of nested groups", () => {
    renderTimeline([run, llm, tool]);
    expect(screen.getByText(/6 events/)).toBeInTheDocument();
  });

  it("hides child groups until their parent is expanded, then shows them", () => {
    renderTimeline([run, llm, tool]);
    expect(screen.queryByText("llm.completed")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("chain.completed"));

    expect(screen.getByText("llm.completed")).toBeInTheDocument();
    expect(screen.getByText("get_weather")).toBeInTheDocument();
  });

  it("interleaves own events and child groups in chronological order", () => {
    renderTimeline([run, llm, tool]);
    fireEvent.click(screen.getByText("chain.completed"));

    const text = document.body.textContent ?? "";
    const order = ["Run started", "llm.completed", "get_weather", "Run completed"].map((s) => text.indexOf(s));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it("keeps groups whose parent is missing visible at the top level", () => {
    const orphan = makeGroup("llm-9", "orphan.group", "missing-parent", [
      makeEvent(9, "llm.completed", "Orphan", "llm-9", "missing-parent"),
    ]);
    renderTimeline([orphan]);
    expect(screen.getByText("orphan.group")).toBeInTheDocument();
  });
});
