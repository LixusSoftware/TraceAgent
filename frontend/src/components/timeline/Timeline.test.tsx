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
    expect(screen.queryByText("LLM call completed")).not.toBeInTheDocument();
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
    expect(screen.getByText("LLM call completed")).toBeInTheDocument();
    expect(screen.getByText("get_weather done")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse all steps" }));
    expect(screen.queryByText("Model call")).not.toBeInTheDocument();
    expect(screen.queryByText("LLM call completed")).not.toBeInTheDocument();
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

  it("shows only the answer row of a model call, not its 'request' row, which only repeats the header", () => {
    const started = { ...makeEvent(3, "llm.started", "Model request to m", "llm-1", "run-1"), status: "running" };
    const model = makeGroup("llm-1", "llm.completed", "run-1", [started, makeEvent(4, "llm.completed", "Model responded via p", "llm-1", "run-1")]);

    renderTimeline([run, model]);
    fireEvent.click(screen.getByRole("button", { name: "Expand all steps" }));

    expect(screen.queryByText("Model request to m")).not.toBeInTheDocument();
    expect((screen.getByText("Model responded via p").closest("button") as HTMLElement)).toHaveTextContent("ok");
  });

  it("shows the result of a tool in the order the tool gave it, with the whole result on hover", () => {
    const done = {
      ...makeEvent(6, "tool.succeeded", '{"ventana": [18.0, 25.0], "veredicto": "causa"}', "tool-1", "run-1"),
      payload_full: { output: { parametro: "tiempo_enfriamiento_s", fuera_de_ventana_pct: 100, veredicto: "causa" } },
    };
    const group = makeGroup("tool-1", "comprobar", "run-1", [makeEvent(5, "tool.started", "Started comprobar.", "tool-1", "run-1"), done]);
    group.tool_name = "comprobar";

    renderTimeline([run, group]);

    const row = screen.getByText(/^→ parametro=/);
    expect(row.textContent).toBe("→ parametro=tiempo_enfriamiento_s, fuera_de_ventana_pct=100, veredicto=causa");
    expect(row).toHaveAttribute("title", expect.stringContaining('"veredicto": "causa"'));
  });

  it("shortens each value of a result instead of cutting the line, so the decisive key is not lost", () => {
    const done = {
      ...makeEvent(6, "tool.succeeded", "x", "tool-1", "run-1"),
      payload_full: { output: { ventana: Array.from({ length: 40 }, (_, i) => i + 0.5), veredicto: "causa" } },
    };
    const group = makeGroup("tool-1", "comprobar", "run-1", [done]);
    group.tool_name = "comprobar";

    renderTimeline([run, group]);

    expect(screen.getByText(/veredicto=causa/)).toBeInTheDocument();
  });

  it("calls the end of an agent what it is, without its Python repr", () => {
    const ended = { ...makeEvent(7, "chain.completed", "Pydantic AI run 'agent' completed", "run-1", null), metadata: { output_summary: "hay_defecto=True evidencia='x'" } };
    const agent = makeGroup("run-1", "chain.completed", null, [makeEvent(2, "chain.started", "Pydantic AI run 'agent' started", "run-1", null), ended]);

    renderTimeline([agent]);

    expect(screen.getByText("Agent finished")).toBeInTheDocument();
    expect(screen.queryByText(/hay_defecto/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Pydantic AI run/)).not.toBeInTheDocument();
  });

  it("shows what a tool returned in its row, so a long run is read without opening every call", () => {
    const withResult = makeGroup("tool-1", "comprobar", "run-1", [
      makeEvent(5, "tool.started", "Started comprobar.", "tool-1", "run-1"),
      makeEvent(6, "tool.succeeded", "veredicto: descartado", "tool-1", "run-1"),
    ]);
    withResult.tool_name = "comprobar";

    renderTimeline([run, withResult]);

    expect(screen.getByText("→ veredicto: descartado")).toBeInTheDocument();
  });

  it("shows a failed tool's reason, and says nothing when the tool returned no output", () => {
    const failed = makeGroup("tool-1", "comprobar", "run-1", [
      makeEvent(5, "tool.started", "Started comprobar.", "tool-1", "run-1"),
      makeEvent(6, "tool.failed", "tag no encontrado", "tool-1", "run-1"),
    ]);
    failed.tool_name = "comprobar";
    const silent = makeGroup("tool-2", "otra", "run-1", [
      makeEvent(7, "tool.started", "Started otra.", "tool-2", "run-1"),
      makeEvent(8, "tool.succeeded", "otra completed.", "tool-2", "run-1"),
    ]);
    silent.tool_name = "otra";

    renderTimeline([run, failed, silent]);

    expect(screen.getByText("→ failed: tag no encontrado")).toBeInTheDocument();
    expect(screen.queryByText(/otra completed/)).not.toBeInTheDocument();
  });

  it("leaves out the 'Started <tool>.' row once the tool has a result, but keeps it while it runs", () => {
    const done = makeGroup("tool-1", "comprobar", "run-1", [
      makeEvent(5, "tool.started", "Started comprobar.", "tool-1", "run-1"),
      makeEvent(6, "tool.succeeded", "veredicto: ok", "tool-1", "run-1"),
    ]);
    done.tool_name = "comprobar";
    const running = makeGroup("tool-2", "lenta", "run-1", [
      makeEvent(7, "tool.started", "Started lenta.", "tool-2", "run-1"),
      makeEvent(8, "tool.started", "Started lenta again.", "tool-2", "run-1"),
    ]);
    running.tool_name = "lenta";

    renderTimeline([run, done, running]);
    fireEvent.click(screen.getByRole("button", { name: "Expand all steps" }));

    expect(screen.queryByText("Started comprobar.")).not.toBeInTheDocument();
    expect(screen.getAllByText("veredicto: ok").length).toBeGreaterThan(0);
    expect(screen.getByText("Started lenta.")).toBeInTheDocument();
  });

  it("interleaves own events and child groups in chronological order", () => {
    renderTimeline([run, llm, tool]);

    const text = document.body.textContent ?? "";
    // The start of the agent ("Run started") is not a row of its own: its header already says so.
    const order = ["Model call", "get_weather", "Agent finished"].map((s) => text.indexOf(s));
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

