/** Data shaping for the Monte Carlo fan chart. Pure functions — no React, no formatting. */

export interface Percentiles {
  dates: string[]
  p10: number[]
  p25: number[]
  p50: number[]
  p75: number[]
  p90: number[]
  deterministic: number[]
}

export interface FanRow {
  date: string
  t: number
  /** [low, high] pairs, the shape recharts' range areas take. */
  outer: [number, number]
  inner: [number, number]
  median: number
  plan: number
}

/**
 * One row per date. `exclude` is subtracted from every series — e.g. property when the page's
 * "Include property" toggle is off. That's exact because property is modelled deterministically,
 * so it shifts every path by the same amount.
 */
export function buildFanRows(mc: Percentiles, exclude: number[] = []): FanRow[] {
  return mc.dates.map((date, i) => {
    const shift = exclude[i] ?? 0
    const at = (series: number[]) => (series[i] ?? 0) - shift
    return {
      date,
      t: new Date(date).getTime(),
      outer: [at(mc.p10), at(mc.p90)],
      inner: [at(mc.p25), at(mc.p75)],
      median: at(mc.p50),
      plan: at(mc.deterministic),
    }
  })
}

/** Legend entries for ChartCard, matching how FanChart draws each part. */
export const FAN_LEGEND = [
  { key: "outer", label: "80% of outcomes", color: "color-mix(in srgb, var(--accent) 25%, transparent)" },
  { key: "inner", label: "50% of outcomes", color: "color-mix(in srgb, var(--accent) 45%, transparent)" },
  { key: "median", label: "Median", color: "var(--accent)", shape: "line" as const },
  { key: "plan", label: "Projection", color: "var(--ink)", shape: "dashed" as const },
]

/** Headline for the end of the range: the 80% band and the median. */
export function fanSummary(rows: FanRow[]): { low: number; median: number; high: number } | null {
  const last = rows[rows.length - 1]
  if (!last) return null
  return { low: last.outer[0], median: last.median, high: last.outer[1] }
}
