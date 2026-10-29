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

  it("opens the first level by itself, so the model calls and tools are visible without a click", () => {
    renderTimeline([run, llm, tool]);

    expect(screen.getByText("Model call")).toBeInTheDocument();
    expect(screen.getByText("get_weather")).toBeInTheDocument();
    // The next level stays closed until asked for.
    expect(screen.queryByText("LLM call started")).not.toBeInTheDocument();
  });

  it("collapses a step by clicking it and opens it again", () => {
    renderTimeline([run, llm, tool]);

    fireEvent.click(screen.getByText("Agent run"));
    expect(screen.queryByText("Model call")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Agent run"));
    expect(screen.getByText("Model call")).toBeInTheDocument();
  });

  it("expands every step with Expand all and closes them with Collapse all", () => {
    renderTimeline([run, llm, tool]);

    fireEvent.click(screen.getByRole("button", { name: "Expand all steps" }));
    expect(screen.getByText("LLM call started")).toBeInTheDocument();
    expect(screen.getByText("get_weather done")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse all steps" }));
    expect(screen.queryByText("Model call")).not.toBeInTheDocument();
    expect(screen.queryByText("LLM call started")).not.toBeInTheDocument();
  });

  it("names the steps for screen readers, with their state", () => {
    renderTimeline([run, llm, tool]);

    expect(screen.getByRole("button", { name: "Agent run, 2 events, expanded" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Model call, 2 events, collapsed" })).toBeInTheDocument();
  });

  it("shows the arguments of a tool in its row", () => {
    const started = {
      ...makeEvent(5, "tool.started", "Started comprobar_parametro.", "tool-1", "run-1"),
      payload_full: { args: { parametro: "temp_molde_C", sentido: "alto" } },
    };
    const withArgs = makeGroup("tool-1", "comprobar_parametro", "run-1", [started, makeEvent(6, "tool.succeeded", "ok", "tool-1", "run-1")]);
    withArgs.tool_name = "comprobar_parametro";

    renderTimeline([run, withArgs]);

    expect(screen.getByText("parametro=temp_molde_C, sentido=alto")).toBeInTheDocument();
  });

  it("gives a command step a short title, with the whole command one hover away", () => {
    const script = "python -c \nimport json\nlineas = leer()\nprint(lineas)";
    const command = makeGroup("cmd-1", script, "run-1", [
      makeEvent(8, "command.started", "Running", "cmd-1", "run-1"),
      makeEvent(9, "command.succeeded", "Done", "cmd-1", "run-1"),
    ]);

    renderTimeline([run, command]);

    const title = screen.getByText("lineas = leer()");
    expect(title.closest("button")).toHaveAttribute("title", script);
  });

  it("does not put a status badge on the group that only says the run started", () => {
    const start = makeGroup("seq-1", "run.started", null, [makeEvent(1, "run.started", "Run created", null, null)]);
    start.status = "running";

    renderTimeline([start]);

    const row = screen.getByText("Run started").closest("button") as HTMLElement;
    expect(row).not.toHaveTextContent(/\brun\b/);
  });

  it("does not put a result badge on a started event", () => {
    const started = { ...makeEvent(5, "tool.started", "Started get_weather.", "tool-1", "run-1"), status: "running" };
    const withStart = makeGroup("tool-1", "get_weather", "run-1", [started, makeEvent(6, "tool.succeeded", "get_weather done", "tool-1", "run-1")]);
    withStart.tool_name = "get_weather";

    renderTimeline([run, withStart]);
    fireEvent.click(screen.getByRole("button", { name: "Expand all steps" }));

    const startedRow = screen.getByText("Started get_weather.").closest("button") as HTMLElement;
    const doneRow = screen.getByText("get_weather done").closest("button") as HTMLElement;
    expect(startedRow).not.toHaveTextContent(/\brun\b/);
    expect(doneRow).toHaveTextContent("ok");
  });

  it("interleaves own events and child groups in chronological order", () => {
    renderTimeline([run, llm, tool]);

    const text = document.body.textContent ?? "";
    const order = ["Run started", "Model call", "get_weather", "Run completed"].map((s) => text.indexOf(s));
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it("keeps groups whose parent is missing visible at the top level", () => {
    const orphan = makeGroup("llm-9", "orphan.group", "missing-parent", [
      makeEvent(9, "llm.completed", "Orphan", "llm-9", "missing-parent"),
    ]);
    renderTimeline([orphan]);
    expect(screen.getByText("Model call")).toBeInTheDocument();
  });
});

