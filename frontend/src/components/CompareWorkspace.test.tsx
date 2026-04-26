import { ReactFlowProvider } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CompareWorkspace } from "./CompareWorkspace";
import { sampleCompareResponse, sampleRuns } from "../test/fixtures";

function renderCompareWorkspace(compareData = sampleCompareResponse) {
  const onSelectionChange = vi.fn();
  render(
    <ReactFlowProvider>
      <CompareWorkspace
        runs={sampleRuns}
        selectedRunId="run-left"
        comparedRunId="run-right"
        compareData={compareData}
        error={null}
        isLoading={false}
        hasComparableRuns
        onSelectLeftRun={vi.fn()}
        onSelectRightRun={vi.fn()}
        onBackToRun={vi.fn()}
        onSelectionChange={onSelectionChange}
      />
    </ReactFlowProvider>
  );
  return { onSelectionChange };
}

describe("CompareWorkspace", () => {
  it("renders divergence, root cause and diff sections", () => {
    renderCompareWorkspace();

    expect(screen.getByText("First divergence")).toBeInTheDocument();
    expect(screen.getByTestId("compare-divergence")).toHaveTextContent("The second run failed its command");
    expect(screen.getByTestId("compare-root-cause")).toHaveTextContent("command_failure");
    expect(screen.getByText("Tool diff")).toBeInTheDocument();
    expect(screen.getByText("Command diff")).toBeInTheDocument();
    expect(screen.getByText("File diff")).toBeInTheDocument();
    expect(screen.getByText("Artifact diff")).toBeInTheDocument();
  });

  it("emits synchronized evidence ids when a compare item is selected", () => {
    const { onSelectionChange } = renderCompareWorkspace();

    fireEvent.click(screen.getByTestId("compare-divergence"));

    expect(onSelectionChange).toHaveBeenCalledWith({
      left: [5],
      right: [15]
    });
  });

  it("degrades cleanly when divergence and file diffs are missing", () => {
    renderCompareWorkspace({
      ...sampleCompareResponse,
      divergence: null,
      file_diff: [],
      artifact_diff: []
    });

    expect(screen.getByTestId("compare-divergence")).toHaveTextContent("No observable divergence between the selected runs.");
    expect(screen.getAllByText("No compare data for this section.").length).toBeGreaterThan(0);
  });
});
