import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BottomPanel } from "./BottomPanel";
import { api } from "../../api";
import type { AuditReport } from "../../types";

vi.mock("../../api", () => ({
  api: { getAudit: vi.fn(), getArtifacts: vi.fn() },
}));

const mocked = vi.mocked(api);

function report(extra: Partial<AuditReport> = {}): AuditReport {
  return {
    run_id: "run-1",
    security_score: 100,
    pii_hit_count: 0,
    injection_hit_count: 0,
    secret_hit_count: 0,
    block_count: 0,
    guardrail_event_count: 0,
    guardrail_events: [],
    flags: [],
    ...extra,
  } as AuditReport;
}

function renderPanel() {
  return render(<BottomPanel selectedRunId="run-1" overview={null} activeTab="audit" onTabChange={() => {}} />);
}

describe("BottomPanel audit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getArtifacts.mockResolvedValue([]);
  });

  it("says nothing was checked when guardrails are off, instead of a meaningless 100/100", async () => {
    mocked.getAudit.mockResolvedValue(report({ guardrails_enabled: false }));

    renderPanel();

    expect(await screen.findByText("Guardrails are off, so nothing was checked.")).toBeInTheDocument();
    expect(screen.getByText("TRACE_AGENT_AUDIT_ENABLE_GUARDRAILS=true")).toBeInTheDocument();
    expect(screen.queryByText("100/100")).not.toBeInTheDocument();
  });

  it("shows the score when guardrails are on, and explains what it rates", async () => {
    mocked.getAudit.mockResolvedValue(report({ guardrails_enabled: true, security_score: 82, pii_hit_count: 2 }));

    renderPanel();

    expect(await screen.findByText("82/100")).toBeInTheDocument();
    expect(screen.getByText("Security Score:")).toHaveAttribute("title", expect.stringContaining("penalty"));
  });

  it("still shows the score for a server that does not say whether guardrails are on", async () => {
    mocked.getAudit.mockResolvedValue(report({ security_score: 90 }));

    renderPanel();

    expect(await screen.findByText("90/100")).toBeInTheDocument();
  });
});
