import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AuditDashboard } from "./AuditDashboard";

describe("AuditDashboard", () => {
  it("renders without crashing when no audit", () => {
    const { container } = render(<AuditDashboard audit={null} isLoading={false} onSelectEvidence={vi.fn()} />);
    expect(container.firstChild).toBeTruthy();
  });

  it("renders without crashing with audit data", () => {
    const audit = {
      run_id: "run-1",
      score: 85,
      security_score: 85,
      pii_hit_count: 0,
      injection_hit_count: 0,
      flags: [],
      checks: [
        { id: "c1", name: "Prompt injection", severity: "low" as const, status: "passed", details: "Clean" },
      ],
      events: [],
      guardrail_events: [],
    } as any;
    const { container } = render(<AuditDashboard audit={audit} isLoading={false} onSelectEvidence={vi.fn()} />);
    expect(container.querySelector(".audit-dashboard")).toBeTruthy();
  });
});
