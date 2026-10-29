import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DashboardView } from "./DashboardView";
import type { DashboardResponse } from "../../types";

function data(extra: Partial<DashboardResponse> = {}, stats: Partial<DashboardResponse["stats"]> = {}): DashboardResponse {
  return {
    stats: {
      total_runs: 4, completed_runs: 3, failed_runs: 1, running_runs: 0, total_errors: 1, total_tools: 9, total_artifacts: 0,
      avg_duration_ms: 126_200, total_prompt_tokens: 24_434, total_completion_tokens: 3_100, total_tokens: 27_534, ...stats,
    },
    trend: [],
    top_tools: [],
    top_errors: [],
    provider_distribution: [{ provider: "openai", count: 4 }],
    model_distribution: [{ model: "gpt-4o", count: 4 }],
    ...extra,
  };
}

describe("DashboardView", () => {
  it("writes the duration like the rest of the interface, not as 126.2s", () => {
    render(<DashboardView data={data()} />);

    expect(screen.getByText("2m 6s")).toBeInTheDocument();
    expect(screen.queryByText("126.2s")).not.toBeInTheDocument();
  });

  it("says what the average counts", () => {
    render(<DashboardView data={data()} />);

    expect(screen.getByText("Avg Duration").closest("div[title]")).toHaveAttribute("title", expect.stringContaining("runs still running are not counted"));
  });

  it("uses one number format everywhere", () => {
    render(<DashboardView data={data()} />);

    expect(screen.getByText("27,534")).toBeInTheDocument();
    // The tokens card talks about tokens only: tool calls have their own card.
    expect(screen.getByText(/27,534 in total/)).toBeInTheDocument();
    expect(screen.queryByText(/tool calls/)).not.toBeInTheDocument();
  });

  it("shows only the cards that have data", () => {
    const { rerender } = render(<DashboardView data={data()} />);
    expect(screen.queryByText("Artifacts")).not.toBeInTheDocument();

    rerender(<DashboardView data={data({}, { total_artifacts: 2 })} />);
    expect(screen.getByText("Artifacts")).toBeInTheDocument();
  });

  it("shows a distribution only when there is more than one thing to compare", () => {
    const { rerender } = render(<DashboardView data={data()} />);
    expect(screen.getByText("Provider Distribution").closest("div")).toHaveClass("hidden");
    expect(screen.getByText("Model Distribution").closest("div")).toHaveClass("hidden");

    rerender(<DashboardView data={data({ provider_distribution: [{ provider: "openai", count: 3 }, { provider: "anthropic", count: 1 }] })} />);
    expect(screen.getByText("Provider Distribution").closest("div")).not.toHaveClass("hidden");
    expect(screen.getByText("Model Distribution").closest("div")).toHaveClass("hidden");
  });
});
