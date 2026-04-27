import { describe, expect, it } from "vitest";
import {
  buildFlow,
  collectToolNames,
  defaultSimilarRunFilters,
  formatDelta,
  formatDuration,
  formatMetadataValue,
  formatMs,
  formatWhen,
  prettifyState,
} from "./view-utils";

describe("formatDuration", () => {
  it("formats seconds only", () => {
    const start = new Date().toISOString();
    const end = new Date(Date.now() + 45_000).toISOString();
    expect(formatDuration(start, end)).toBe("45s");
  });

  it("formats minutes and seconds", () => {
    const start = new Date().toISOString();
    const end = new Date(Date.now() + 125_000).toISOString();
    expect(formatDuration(start, end)).toBe("2m 5s");
  });

  it("uses now when endedAt is null", () => {
    const start = new Date(Date.now() - 10_000).toISOString();
    const result = formatDuration(start, null);
    expect(result.endsWith("s")).toBe(true);
  });
});

describe("formatWhen", () => {
  it("returns - for null", () => {
    expect(formatWhen(null)).toBe("-");
  });

  it("formats a timestamp", () => {
    const ts = "2026-04-26T10:00:00Z";
    const result = formatWhen(ts);
    expect(result).toContain("26");
  });
});

describe("formatMs", () => {
  it("returns - for null", () => {
    expect(formatMs(null)).toBe("-");
  });

  it("formats milliseconds", () => {
    expect(formatMs(500)).toBe("500 ms");
  });

  it("formats seconds", () => {
    expect(formatMs(1500)).toBe("1.5 s");
  });

  it("formats minutes", () => {
    expect(formatMs(125_000)).toBe("2m 5s");
  });
});

describe("prettifyState", () => {
  it("returns unknown for null", () => {
    expect(prettifyState(null)).toBe("unknown");
  });

  it("replaces underscores with spaces", () => {
    expect(prettifyState("tool_use")).toBe("tool use");
  });
});

describe("formatMetadataValue", () => {
  it("returns - for null", () => {
    expect(formatMetadataValue(null)).toBe("-");
  });

  it("returns string as-is", () => {
    expect(formatMetadataValue("hello")).toBe("hello");
  });

  it("formats number", () => {
    expect(formatMetadataValue(42)).toBe("42");
  });

  it("formats array", () => {
    expect(formatMetadataValue(["a", "b"])).toBe("a, b");
  });

  it("formats object as JSON", () => {
    expect(formatMetadataValue({ a: 1 })).toBe('{"a":1}');
  });
});

describe("collectToolNames", () => {
  it("returns empty for null", () => {
    expect(collectToolNames(null)).toEqual([]);
  });

  it("collects unique sorted tool names", () => {
    const overview = {
      tool_chain: [
        { tool_name: "search" },
        { tool_name: "patch" },
        { tool_name: "search" },
      ],
    } as any;
    expect(collectToolNames(overview)).toEqual(["patch", "search"]);
  });
});

describe("formatDelta", () => {
  it("returns same when diff is 0", () => {
    expect(formatDelta(5, 5)).toBe("same");
  });

  it("returns positive diff", () => {
    expect(formatDelta(5, 8, "ms")).toBe("+3 ms");
  });

  it("returns negative diff", () => {
    expect(formatDelta(8, 5)).toBe("-3");
  });
});

describe("buildFlow", () => {
  it("returns empty for null graph", () => {
    const result = buildFlow(null);
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it("builds nodes and edges from graph", () => {
    const graph = {
      nodes: [
        { id: "n1", type: "event", label: "start", position: { x: 0, y: 0 }, data: {} },
      ],
      edges: [
        { id: "e1", source: "n1", target: "n2", label: "next", animated: false },
      ],
    } as any;
    const result = buildFlow(graph);
    expect(result.nodes.length).toBe(1);
    expect(result.edges.length).toBe(1);
    expect(result.nodes[0].id).toBe("n1");
  });
});

describe("defaultSimilarRunFilters", () => {
  it("has expected defaults", () => {
    expect(defaultSimilarRunFilters.sameAgentOnly).toBe(false);
    expect(defaultSimilarRunFilters.status).toBe("all");
    expect(defaultSimilarRunFilters.minScore).toBe(0.15);
  });
});
