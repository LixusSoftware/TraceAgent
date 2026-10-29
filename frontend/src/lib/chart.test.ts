import { describe, expect, it } from "vitest"
import { dayLabel, formatCount, niceTicks } from "./chart"

describe("dayLabel", () => {
  it("writes a day like the other dates of the interface", () => {
    expect(dayLabel("2026-10-28")).toBe("28 Oct")
    expect(dayLabel("2026-01-05")).toBe("5 Jan")
  })

  it("keeps what it cannot read", () => {
    expect(dayLabel("not a day")).toBe("not a day")
  })
})

describe("formatCount", () => {
  it("always groups thousands the same way, whatever the language of the browser", () => {
    expect(formatCount(24434)).toBe("24,434")
    expect(formatCount(1157818)).toBe("1,157,818")
    expect(formatCount(7)).toBe("7")
  })
})

describe("niceTicks", () => {
  it("uses round values, not a fraction of the maximum", () => {
    expect(niceTicks(26000)).toEqual([0, 10000, 20000, 30000])
    expect(niceTicks(101855)).toEqual([0, 50000, 100000, 150000])
  })

  it("covers the maximum with the last mark", () => {
    for (const max of [3, 17, 840, 26000, 999999]) {
      const ticks = niceTicks(max)
      expect(ticks[0]).toBe(0)
      expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(max)
      expect(ticks.length).toBeLessThanOrEqual(7)
    }
  })

  it("handles small counts without fractions", () => {
    expect(niceTicks(3)).toEqual([0, 1, 2, 3, 4].slice(0, niceTicks(3).length))
    expect(niceTicks(3).every(Number.isInteger)).toBe(true)
  })

  it("does not break on nothing to draw", () => {
    expect(niceTicks(0)).toEqual([0, 1])
    expect(niceTicks(NaN)).toEqual([0, 1])
  })
})
