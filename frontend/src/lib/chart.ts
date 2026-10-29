/** One number format for the whole interface (the browser's own would mix `1,234` and `1.234` on one screen). */
export function formatCount(value: number): string {
  return value.toLocaleString("en-GB")
}

/** A day (2026-10-28) written like the dates of the rest of the interface: "28 Oct". */
export function dayLabel(isoDay: string): string {
  const day = new Date(`${isoDay}T12:00:00`)
  return Number.isNaN(day.getTime()) ? isoDay : day.toLocaleDateString("en-GB", { day: "numeric", month: "short" })
}

/** Axis marks at round values (0, 5 000, 10 000...) up to the first one that covers `max`. */
export function niceTicks(max: number, target = 4): number[] {
  if (!Number.isFinite(max) || max <= 0) return [0, 1]
  const rough = max / target
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = ([1, 2, 5, 10].find((factor) => factor * magnitude >= rough) ?? 10) * magnitude
  const ticks: number[] = []
  for (let value = 0; value < max + step; value += step) ticks.push(Math.round(value * 1e6) / 1e6)
  return ticks.slice(0, ticks.findIndex((tick) => tick >= max) + 1)
}
