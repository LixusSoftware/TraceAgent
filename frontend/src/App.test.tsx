import { ReactFlowProvider } from "@xyflow/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  sampleAnalytics,
  sampleArtifacts,
  sampleCompareResponse,
  sampleExplanation,
  sampleGraph,
  sampleRunOverview,
  sampleRuns,
  sampleTimeline
} from "./test/fixtures";

const apiMocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
  createRun: vi.fn(),
  createTurn: vi.fn(),
  finishRun: vi.fn(),
  getRun: vi.fn(),
  getTimeline: vi.fn(),
  getGraph: vi.fn(),
  getAnalytics: vi.fn(),
  compareRuns: vi.fn(),
  getExplanation: vi.fn(),
  getArtifacts: vi.fn()
}));

vi.mock("./api", () => ({
  api: apiMocks
}));

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    apiMocks.listRuns.mockResolvedValue(sampleRuns);
    apiMocks.createRun.mockResolvedValue({ run_id: "run-launch", status: "running" });
    apiMocks.createTurn.mockResolvedValue({
      status: "message",
      assistant_message: { role: "assistant", content: "Hola desde launcher" },
      tool_calls: []
    });
    apiMocks.finishRun.mockResolvedValue({ status: "completed", run_id: "run-launch", decisions: 1 });
    apiMocks.getRun.mockResolvedValue(sampleRunOverview);
    apiMocks.getTimeline.mockResolvedValue(sampleTimeline);
    apiMocks.getGraph.mockResolvedValue(sampleGraph);
    apiMocks.getAnalytics.mockResolvedValue(sampleAnalytics);
    apiMocks.compareRuns.mockResolvedValue(sampleCompareResponse);
    apiMocks.getExplanation.mockResolvedValue(sampleExplanation);
    apiMocks.getArtifacts.mockResolvedValue(sampleArtifacts);
  });

  it("opens compare mode from similar runs and syncs evidence selection", async () => {
    render(
      <ReactFlowProvider>
        <App />
      </ReactFlowProvider>
    );

    expect(await screen.findByRole("heading", { name: "Patch app.py and run tests" })).toBeInTheDocument();
    fireEvent.click(await screen.findByText("Comparar"));

    expect(await screen.findByText("Compare workspace")).toBeInTheDocument();
    await waitFor(() => {
      expect(apiMocks.compareRuns).toHaveBeenCalledWith("run-left", "run-right");
    });

    fireEvent.click(screen.getByTestId("compare-divergence"));

    expect(await screen.findByText("Left evidence")).toBeInTheDocument();
    expect(screen.getAllByText("Tests passed.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Tests failed after wrong edit.").length).toBeGreaterThan(0);
  });

  it("launches a run directly from the frontend form", async () => {
    apiMocks.listRuns
      .mockResolvedValueOnce(sampleRuns)
      .mockResolvedValueOnce([
        {
          id: "run-launch",
          agent_name: "lmstudio-local-agent",
          goal: "Live prompt: Hola desde formulario",
          status: "completed",
          started_at: "2026-04-18T09:00:00Z",
          ended_at: "2026-04-18T09:00:03Z",
          tool_count: 0,
          error_count: 0,
          retry_count: 0,
          artifact_count: 0,
          model: "google/gemma-4-e4b",
          provider: "openai"
        }
      ]);

    render(
      <ReactFlowProvider>
        <App />
      </ReactFlowProvider>
    );

    await screen.findByRole("heading", { name: "Patch app.py and run tests" });
    fireEvent.change(screen.getByLabelText("Goal"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "google/gemma-4-e4b" } });
    fireEvent.change(screen.getByLabelText("User prompt"), { target: { value: "Hola desde formulario" } });
    fireEvent.submit(screen.getByTestId("launcher-form"));

    await waitFor(() => {
      expect(apiMocks.createRun).toHaveBeenCalledWith(
        expect.objectContaining({
          agent_name: "lmstudio-local-agent",
          goal: "Live prompt: Hola desde formulario"
        })
      );
    });

    expect(apiMocks.createTurn).toHaveBeenCalledWith(
      "run-launch",
      expect.objectContaining({ model: "google/gemma-4-e4b", provider: "openai" })
    );
    expect(apiMocks.finishRun).toHaveBeenCalledWith(
      "run-launch",
      expect.objectContaining({ role: "assistant", content: "Hola desde launcher" })
    );
    expect(await screen.findByText("Run created and completed. It is now visible in the run list.")).toBeInTheDocument();
  });
});
