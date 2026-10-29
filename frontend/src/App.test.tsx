import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import App from "./App";
import { api } from "./api";
import type { EventItem, RunListItem, RunOverview, TimelineResponse } from "./types";

vi.mock("./api", () => ({
  api: {
    listRuns: vi.fn(),
    getRun: vi.fn(),
    getTimeline: vi.fn(),
    getAudit: vi.fn(),
    getArtifacts: vi.fn(),
    getGraph: vi.fn(),
    getDashboard: vi.fn(),
    compareRuns: vi.fn(),
  },
}));

const mocked = vi.mocked(api);

// jsdom has no matchMedia, which the theme provider asks for.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

function run(id: string, name: string): RunListItem {
  return {
    id,
    agent_name: name,
    goal: `goal of ${name}`,
    status: "completed",
    started_at: "2026-10-23T10:00:00",
    ended_at: "2026-10-23T10:00:05",
    tool_count: 1,
    error_count: 0,
    retry_count: 0,
    artifact_count: 0,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    model: null,
    provider: null,
  };
}

function overview(item: RunListItem): RunOverview {
  return {
    ...item,
    redaction_level: "summary",
    metadata: {},
    final_output_summary: null,
    flags: [],
    execution: { duration_ms: 5000, model_turn_count: 1, command_count: 0 },
    tool_chain: [],
    command_chain: [],
    file_activity: [],
    patch_activity: [],
  } as unknown as RunOverview;
}

function event(id: number, summary: string): EventItem {
  return {
    id,
    seq: id,
    timestamp: "2026-10-23T10:00:00",
    step_id: `step-${id}`,
    parent_step_id: null,
    actor: "otlp",
    type: "tool.succeeded",
    summary,
    status: "succeeded",
    duration_ms: 5,
    provider: null,
    model: null,
    tool_name: "get_weather",
    artifact_refs: [],
    error_code: null,
    payload_hash: null,
    payload_full: null,
    metadata: {},
  };
}

function timeline(runId: string, item: EventItem): TimelineResponse {
  return {
    run_id: runId,
    groups: [
      {
        step_id: item.step_id as string,
        label: "get_weather",
        status: "succeeded",
        step_type: "tool",
        tool_name: "get_weather",
        call_id: null,
        parent_step_id: null,
        event_count: 2,
        started_at: item.timestamp,
        ended_at: item.timestamp,
        duration_ms: 5,
        events: [item, { ...item, id: item.id + 1000, summary: `${item.summary} (end)` }],
      },
    ],
  };
}

describe("App", () => {
  const first = run("run-1", "first-agent");
  const second = run("run-2", "second-agent");

  beforeEach(() => {
    vi.clearAllMocks();
    mocked.listRuns.mockResolvedValue([first, second]);
    mocked.getRun.mockImplementation(async (id: string) => overview(id === "run-1" ? first : second));
    mocked.getTimeline.mockImplementation(async (id: string) =>
      timeline(id, event(id === "run-1" ? 1 : 2, id === "run-1" ? "weather in Madrid" : "weather in Paris")),
    );
    mocked.getAudit.mockRejectedValue(new Error("no audit report in this test"));
    mocked.getArtifacts.mockResolvedValue([]);
  });

  function renderApp() {
    return render(
      <ThemeProvider attribute="class">
        <App />
      </ThemeProvider>,
    );
  }

  it("opens the first run and shows its timeline", async () => {
    renderApp();

    // The first level is open, so the events of the step are visible without a click.
    expect(await screen.findByText("weather in Madrid")).toBeInTheDocument();
    expect(mocked.getTimeline).toHaveBeenCalledWith("run-1");
  });

  it("does not keep showing the event selected in another run in the inspector", async () => {
    renderApp();

    // Inspect one of the events of the first run.
    fireEvent.click(await screen.findByText("weather in Madrid"));
    await waitFor(() => expect(screen.getAllByText("weather in Madrid").length).toBeGreaterThan(1));

    // Switch to the second run: its own overview shows, not the event of the first.
    fireEvent.click(screen.getByText("second-agent"));
    await screen.findByText("goal of second-agent", { selector: "p.text-xs" });

    expect(screen.queryByText("weather in Madrid")).not.toBeInTheDocument();
  });

  it("does not show the previous run's data in the inspector while the next run loads", async () => {
    let finishLoading: (value: RunOverview) => void = () => {};
    renderApp();
    await screen.findByText("weather in Madrid");

    mocked.getRun.mockImplementationOnce(() => new Promise<RunOverview>((resolve) => { finishLoading = resolve }));
    fireEvent.click(screen.getByText("second-agent"));

    // While the second run is loading, nothing of the first one is left on screen.
    expect(await screen.findAllByText("Loading run...")).not.toHaveLength(0);
    expect(screen.queryByText("goal of first-agent", { selector: "p.text-xs" })).not.toBeInTheDocument();

    finishLoading(overview(second));
    expect(await screen.findByText("goal of second-agent", { selector: "p.text-xs" })).toBeInTheDocument();
  });

  it("goes back to the run in the inspector when the view changes, instead of keeping the event of the other view", async () => {
    mocked.getGraph.mockResolvedValue({ run_id: "run-1", view: "execution", nodes: [], edges: [] });
    renderApp();
    fireEvent.click(await screen.findByText("weather in Madrid"));
    await waitFor(() => expect(screen.getAllByText("weather in Madrid").length).toBeGreaterThan(1));

    fireEvent.click(screen.getByRole("button", { name: "Graph" }));

    expect(await screen.findByText("goal of first-agent", { selector: "p.text-xs" })).toBeInTheDocument();
  });

  it("names every run in the list for screen readers, with its state", async () => {
    renderApp();

    expect(await screen.findByRole("button", { name: "first-agent, completed: goal of first-agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "second-agent, completed: goal of second-agent" })).toBeInTheDocument();
  });

  it("refreshes the list of runs every few seconds so a new run shows up while it runs", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderApp();
      await screen.findByText("weather in Madrid");
      const before = mocked.listRuns.mock.calls.length;

      await vi.advanceTimersByTimeAsync(3500);

      expect(mocked.listRuns.mock.calls.length).toBeGreaterThan(before);
    } finally {
      vi.useRealTimers();
    }
  });
});
