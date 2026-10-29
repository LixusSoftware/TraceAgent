import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExecutionGraph } from "./ExecutionGraph";
import { api } from "../../api";

vi.mock("../../api", () => ({
  api: { getGraph: vi.fn() },
}));

const mocked = vi.mocked(api);

describe("ExecutionGraph without nodes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getGraph.mockResolvedValue({ run_id: "run-1", view: "decisions", nodes: [], edges: [] });
  });

  it("explains that the decisions of a run that is still running do not exist yet", async () => {
    render(<ExecutionGraph runId="run-1" view="decisions" runStatus="running" />);

    expect(await screen.findByText("Decisions appear when the run finishes.")).toBeInTheDocument();
    expect(screen.getByText(/still running/)).toBeInTheDocument();
  });

  it("keeps the plain message for a finished run, or for the execution graph", async () => {
    const { unmount } = render(<ExecutionGraph runId="run-1" view="decisions" runStatus="completed" />);
    expect(await screen.findByText("No graph data available.")).toBeInTheDocument();
    unmount();

    render(<ExecutionGraph runId="run-1" view="execution" runStatus="running" />);
    expect(await screen.findByText("No graph data available.")).toBeInTheDocument();
  });
});
