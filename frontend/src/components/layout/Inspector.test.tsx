import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Inspector } from "./Inspector";
import type { EventItem, GraphNode } from "../../types";

function event(extra: Partial<EventItem> = {}): EventItem {
  return {
    id: 7, seq: 1, timestamp: "2026-10-23T10:00:00", step_id: "step-abc", parent_step_id: "parent-xyz", actor: "otlp",
    type: "tool.succeeded", summary: "get_weather finished", status: "succeeded", duration_ms: 120, provider: null,
    model: null, tool_name: "get_weather", artifact_refs: [], error_code: null, payload_hash: null, payload_full: null,
    metadata: {}, ...extra,
  };
}

const decision: GraphNode = {
  id: "decision-eac540a0", type: "decision", label: "Retried lookup", position: { x: 480, y: 60 },
  data: { kind: "retry", summary: "The lookup failed once, so it was tried again", decisionId: 3, evidenceIds: [7], outcome: "retry" },
};

describe("Inspector", () => {
  it("shows what a decision means and hides ids and coordinates until asked", () => {
    render(<Inspector overview={null} selectedEvent={null} selectedGraphNode={decision} events={[event()]} />);

    expect(screen.getByText("Retried lookup")).toBeInTheDocument();
    expect(screen.getByText("The lookup failed once, so it was tried again")).toBeInTheDocument();
    expect(screen.getByText("Retried")).toBeInTheDocument();
    expect(screen.getByText("Tool finished")).toBeInTheDocument();
    // The raw identifiers are folded away.
    expect(screen.getByText("decision-eac540a0")).not.toBeVisible();
  });

  it("opens the event a decision is based on", () => {
    const onSelectEvent = vi.fn();
    render(<Inspector overview={null} selectedEvent={null} selectedGraphNode={decision} events={[event()]} onSelectEvent={onSelectEvent} />);

    fireEvent.click(screen.getByText("Tool finished"));
    expect(onSelectEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
  });

  it("shows an event by what happened, with its ids folded away", () => {
    render(<Inspector overview={null} selectedEvent={event()} />);

    expect(screen.getByText("Tool finished")).toBeInTheDocument();
    expect(screen.getByText("get_weather finished")).toBeInTheDocument();
    expect(screen.getByText("Succeeded")).toBeInTheDocument();
    expect(screen.getByText("step-abc")).not.toBeVisible();
  });

  it("shows the error of a failed event", () => {
    render(<Inspector overview={null} selectedEvent={event({ type: "tool.failed", status: "failed", error_code: "ValueError" })} />);

    expect(screen.getByText("Error: ValueError")).toBeInTheDocument();
  });
});
