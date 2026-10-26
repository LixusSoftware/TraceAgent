import { describe, expect, it } from "vitest";
import {
  decisionKindLabel,
  eventNodeLabel,
  eventTitle,
  groupTitle,
  outcomeLabel,
  statusLabel,
  tokensLabel,
} from "./humanize";
import type { EventItem, TimelineGroup } from "../types";

function event(type: string, extra: Partial<EventItem> = {}): EventItem {
  return {
    id: 1, seq: 1, timestamp: "2026-10-23T10:00:00", step_id: "s", parent_step_id: null, actor: "otlp", type,
    summary: "", status: null, duration_ms: null, provider: null, model: null, tool_name: null, artifact_refs: [],
    error_code: null, payload_hash: null, payload_full: null, metadata: {}, ...extra,
  };
}

function group(label: string, events: EventItem[], toolName: string | null = null): TimelineGroup {
  return {
    step_id: "s", label, status: "succeeded", step_type: "run", tool_name: toolName, call_id: null, parent_step_id: null,
    event_count: events.length, started_at: "", ended_at: "", duration_ms: null, events,
  };
}

describe("eventTitle", () => {
  it("uses plain names for known events", () => {
    expect(eventTitle("llm.completed")).toBe("Model response");
    expect(eventTitle("tool.failed")).toBe("Tool failed");
    expect(eventTitle("chain.started")).toBe("Agent started");
    expect(eventTitle("run.completed")).toBe("Run finished");
  });

  it("makes an unknown type readable instead of showing it raw", () => {
    expect(eventTitle("guardrail.blocked")).toBe("Guardrail blocked");
    expect(eventTitle("custom_thing")).toBe("Custom thing");
  });
});

describe("labels", () => {
  it("names decision kinds and outcomes", () => {
    expect(decisionKindLabel("tool_choice")).toBe("Tool choice");
    expect(decisionKindLabel("retry")).toBe("Retry");
    expect(outcomeLabel("requested")).toBe("Requested");
    expect(outcomeLabel("retry")).toBe("Retried");
    expect(outcomeLabel(null)).toBe("—");
  });

  it("names statuses", () => {
    expect(statusLabel("succeeded")).toBe("Succeeded");
    expect(statusLabel("failed")).toBe("Failed");
    expect(statusLabel(null)).toBe("—");
  });
});

describe("groupTitle", () => {
  it("keeps the tool name for tools", () => {
    expect(groupTitle(group("get_weather", [event("tool.started"), event("tool.succeeded")], "get_weather"))).toBe("get_weather");
  });

  it("calls an agent group an agent run, with the agent's name", () => {
    const events = [event("chain.started", { metadata: { agent_name: "weather-agent" } }), event("chain.completed")];
    expect(groupTitle(group("chain.completed", events))).toBe("Agent run · weather-agent");
    expect(groupTitle(group("chain.completed", [event("chain.started")]))).toBe("Agent run");
  });

  it("calls a model group a model call, with the model", () => {
    const events = [event("llm.started", { model: "gpt-4o" }), event("llm.completed")];
    expect(groupTitle(group("llm.completed", events))).toBe("Model call · gpt-4o");
  });

  it("describes the start and end of a run", () => {
    expect(groupTitle(group("run.started", [event("run.started")]))).toBe("Run started");
    expect(groupTitle(group("run.completed", [event("run.completed")]))).toBe("Run finished");
  });

  it("keeps the server label for commands and files, which are already readable", () => {
    expect(groupTitle(group("src/app.py", [event("file.written")]))).toBe("src/app.py");
  });
});

describe("eventNodeLabel / tokensLabel", () => {
  it("adds the tool to a graph node", () => {
    expect(eventNodeLabel("tool.succeeded", "get_weather")).toBe("Tool finished · get_weather");
    expect(eventNodeLabel("llm.completed", null)).toBe("Model response");
  });

  it("formats tokens only when the event has them", () => {
    expect(tokensLabel(event("llm.completed", { metadata: { prompt_tokens: 242, completion_tokens: 41 } }))).toBe("242 in · 41 out");
    expect(tokensLabel(event("tool.succeeded"))).toBeNull();
  });
});
