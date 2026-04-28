import { describe, it, expect } from "vitest";
import { formatDuration, formatWhen, formatMs } from "./utils";

describe("formatDuration", () => {
  it("returns — for null", () => {
    expect(formatDuration(null)).toBe("—");
  });
  it("formats milliseconds", () => {
    expect(formatDuration(500)).toBe("500ms");
  });
  it("formats seconds", () => {
    expect(formatDuration(3000)).toBe("3s");
  });
  it("formats minutes and seconds", () => {
    expect(formatDuration(125000)).toBe("2m 5s");
  });
  it("formats hours", () => {
    expect(formatDuration(3661000)).toBe("1h 1m 1s");
  });
});

describe("formatWhen", () => {
  it("returns — for null", () => {
    expect(formatWhen(null)).toBe("—");
  });
  it("formats an ISO date", () => {
    const result = formatWhen("2024-01-15T10:30:00Z");
    expect(result).toMatch(/\d{1,2}/);
    expect(result).toContain("15");
  });
});

describe("formatMs", () => {
  it("returns — for null", () => {
    expect(formatMs(null)).toBe("—");
  });
  it("formats milliseconds", () => {
    expect(formatMs(800)).toBe("800ms");
  });
  it("formats seconds", () => {
    expect(formatMs(2500)).toBe("2.5s");
  });
});
