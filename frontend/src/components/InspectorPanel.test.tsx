import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InspectorPanel } from "./InspectorPanel";

describe("InspectorPanel", () => {
  const baseProps = {
    workspaceMode: "run" as const,
    overview: null,
    explanation: null,
    artifacts: [],
    selectedEvents: [],
    selectedPrimaryEvent: null,
    compareLeftEvents: [],
    compareRightEvents: [],
    comparePrimaryLeftEvent: null,
    comparePrimaryRightEvent: null,
    onSelectEvidence: vi.fn(),
  };

  it("renders without crashing when no overview", () => {
    const { container } = render(<InspectorPanel {...baseProps} />);
    expect(container.firstChild).toBeTruthy();
  });

  it("renders without crashing with overview", () => {
    const overview = {
      id: "run-1",
      agent_name: "test-agent",
      goal: "Test goal",
      status: "completed",
      provider: "openai",
      model: "gpt-4",
      redaction_level: "summary",
      tool_count: 2,
      error_count: 0,
      retry_count: 0,
      artifact_count: 1,
      total_prompt_tokens: 100,
      total_completion_tokens: 50,
      started_at: "2026-04-26T10:00:00Z",
      ended_at: "2026-04-26T10:02:00Z",
      metadata: {},
      final_output_summary: "Tests passed.",
      flags: [],
      execution: {
        duration_ms: 120000,
        total_event_count: 8,
        model_turn_count: 2,
        assistant_turn_count: 2,
        tool_request_count: 1,
        tool_success_count: 1,
        tool_failure_count: 0,
        command_count: 1,
        command_failure_count: 0,
        file_read_count: 1,
        file_write_count: 1,
        patch_count: 1,
        registered_tool_count: 1,
        current_state: "completed",
        last_event_type: "run.completed",
        last_event_actor: "proxy",
        last_event_at: "2026-04-26T10:02:00Z",
        token_usage: {
          prompt_tokens: 10,
          completion_tokens: 20,
          total_tokens: 30,
          reasoning_tokens: 5,
        },
      },
      tool_chain: [],
      command_chain: [],
      file_activity: [],
      patch_activity: [],
    };
    const { container } = render(<InspectorPanel {...baseProps} overview={overview as any} />);
    expect(container.firstChild).toBeTruthy();
  });
});
