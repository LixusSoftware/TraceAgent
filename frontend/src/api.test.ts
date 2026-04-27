import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("listRuns builds query params", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: "run-1" }],
    } as Response);

    await api.listRuns({ limit: 10, offset: 5, status: "completed", search: "test" });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs?limit=10&offset=5&status=completed&search=test"),
      expect.any(Object)
    );
  });

  it("getDashboard uses default period", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ stats: {}, trend: [], top_tools: [], top_errors: [], providers: [], models: [] }),
    } as Response);

    await api.getDashboard();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/dashboard?period=24h"),
      expect.any(Object)
    );
  });

  it("getTurns constructs correct URL", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    } as Response);

    await api.getRunTurns("run-123");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/runs/run-123/turns"),
      expect.any(Object)
    );
  });

  it("throws on non-ok response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not found" }),
    } as Response);

    await expect(api.getRun("nonexistent")).rejects.toThrow("Request failed: 404");
  });
});
