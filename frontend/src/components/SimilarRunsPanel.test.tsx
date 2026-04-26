import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SimilarRunsPanel } from "./SimilarRunsPanel";
import { sampleAnalytics } from "../test/fixtures";
import { defaultSimilarRunFilters } from "../view-utils";

describe("SimilarRunsPanel", () => {
  it("updates filters through the provided callback", () => {
    const onFiltersChange = vi.fn();
    render(
      <SimilarRunsPanel
        analytics={sampleAnalytics}
        comparedRunId={null}
        filters={defaultSimilarRunFilters}
        onFiltersChange={onFiltersChange}
        onCompare={vi.fn()}
        onOpen={vi.fn()}
      />
    );

    fireEvent.click(screen.getByLabelText("Same agent"));
    expect(onFiltersChange).toHaveBeenCalledWith({
      ...defaultSimilarRunFilters,
      sameAgentOnly: true
    });

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "failed" } });
    expect(onFiltersChange).toHaveBeenCalledWith({
      ...defaultSimilarRunFilters,
      status: "failed"
    });
  });

  it("opens compare mode from a similar run card", () => {
    const onCompare = vi.fn();
    render(
      <SimilarRunsPanel
        analytics={sampleAnalytics}
        comparedRunId={null}
        filters={defaultSimilarRunFilters}
        onFiltersChange={vi.fn()}
        onCompare={onCompare}
        onOpen={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText("Comparar"));
    expect(onCompare).toHaveBeenCalledWith("run-right");
  });
});
