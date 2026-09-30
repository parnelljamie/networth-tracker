/** Pure data shaping for AreaStackChart: rows, axis ranges and ticks. No React, no formatting,
 *  so each rule the chart relies on can be unit-tested. */

export type ChartRow = Record<string, number | string | null>

export interface ChartSeriesValues {
  label: string
  values: number[]
}

export const MS_PER_YEAR = 365.25 * 24 * 60 * 60 * 1000

/** A round tick step (1, 2, 2.5 or 5 × a power of ten) close to `rough`. */
export function niceStep(rough: number): number {
  if (!(rough > 0)) return 1
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const n = rough / magnitude
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * magnitude
}

/** Y-axis range and round ticks for what is actually drawn. A negative too small to see at this
 *  scale (e.g. a £500 card balance on a £600k chart) doesn't drag the axis down a whole step. */
export function valueAxis(
  data: ChartRow[],
  keys: string[],
  stacked: boolean
): { domain: [number, number]; ticks: number[] } {
  const values: number[] = []
  for (const row of data) {
    if (stacked) {
      // Stacked areas reach the running sums of positives and of negatives.
      let pos = 0
      let neg = 0
      for (const k of keys) {
        const v = row[k]
        if (typeof v !== "number") continue
        if (k === "Total" || k === "Projected") values.push(v)
        else if (v >= 0) pos += v
        else neg += v
      }
      values.push(pos, neg)
    } else {
      for (const k of keys) {
        const v = row[k]
        if (typeof v === "number") values.push(v)
      }
    }
  }
  if (values.length === 0) values.push(0)
  let lo: number
  let hi: number
  let step: number
  if (stacked) {
    // Stacked areas fill from zero, so zero stays on the axis.
    lo = Math.min(0, ...values)
    hi = Math.max(0, ...values)
    if (hi === lo) hi = lo + 1
    step = niceStep((hi - lo) / 4)
    if (lo < 0 && -lo < step * 0.1) lo = 0
    if (hi > 0 && hi < step * 0.1) hi = 0
  } else {
    // Lines: fit the range actually drawn, with a little headroom, so hiding the low series
    // lifts the minimum as well as lowering the maximum.
    const positive = values.filter((v) => v > 0)
    lo = positive.length ? Math.min(...positive) : 0
    hi = positive.length ? Math.max(...positive) : 1
    const pad = hi > lo ? (hi - lo) * 0.05 : Math.max(Math.abs(hi) * 0.02, 1)
    step = niceStep((hi - lo + 2 * pad) / 4)
    // Never below zero: debts such as a credit card sit off the bottom rather than stretching
    // the axis down. Keep a zero baseline when the data already sits close to it.
    lo = lo - pad < step ? 0 : lo - pad
    hi = Math.max(hi + pad, step)
  }
  const min = Math.floor(lo / step) * step
  const max = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let v = min; v <= max + step / 2; v += step) ticks.push(v)
  return { domain: [min, max], ticks }
}

export function pointCount(data: ChartRow[], key: string): number {
  return data.reduce((n, row) => n + (typeof row[key] === "number" ? 1 : 0), 0)
}

export type AgePrecision = "years" | "months"

/**
 * A person's age at a tick, in units people actually use: "42" over a long range, "42y 7m" when
 * the range is short enough that whole years would all read the same. Never decimal years —
 * "42.58" is not an age. Calendar months, not a division by the average year length, so the
 * figure turns over on the birthday and on each monthiversary.
 */
export function ageAt(dateOfBirth: string, t: number, precision: AgePrecision): string {
  const dob = new Date(toTime(dateOfBirth))
  const at = new Date(t)
  let months =
    (at.getUTCFullYear() - dob.getUTCFullYear()) * 12 + (at.getUTCMonth() - dob.getUTCMonth())
  if (at.getUTCDate() < dob.getUTCDate()) months -= 1
  if (months < 0) months = 0
  const years = Math.floor(months / 12)
  return precision === "years" ? String(years) : `${years}y ${months % 12}m`
}

/** Dates are plotted on a true time scale, so daily history and monthly projection points
 *  sit at their real distance apart instead of one slot each. */
export function toTime(iso: string): number {
  return new Date(iso).getTime()
}

/** Evenly spaced tick positions across [start, end]; recharts' own number ticks ignore dates. */
export function timeTicks(start: number, end: number, count = 5): number[] {
  if (end <= start) return [start]
  const step = (end - start) / (count - 1)
  return Array.from({ length: count }, (_, i) => Math.round(start + step * i))
}

/** One row per history date (`date`, time `t`, `Total`, one key per series label), then the
 *  projection's later dates as rows carrying only `Projected`. */
export function buildChartRows(
  dates: string[],
  series: ChartSeriesValues[],
  total: number[],
  projection?: { dates: string[]; total: number[] }
): ChartRow[] {
  // A series isn't drawn before its first non-zero value: otherwise an account added recently
  // draws a £0 line from the start of the range, on top of (and hiding) the series below it.
  const firstIndex = new Map(
    series.map((s) => [s.label, s.values.findIndex((v) => Math.abs(v ?? 0) > 0.005)])
  )
  const data: ChartRow[] = dates.map((d, i) => {
    const row: ChartRow = { date: d, t: toTime(d), Total: total[i] ?? 0 }
    for (const s of series) {
      const first = firstIndex.get(s.label) ?? -1
      row[s.label] = first === -1 || i < first ? null : (s.values[i] ?? 0)
    }
    return row
  })

  if (projection && projection.dates.length > 0) {
    // Seed the dashed line at the last historical point so it connects to the solid line.
    const lastRow = data[data.length - 1]
    if (lastRow) lastRow.Projected = lastRow.Total
    const lastTime = lastRow ? (lastRow.t as number) : -Infinity
    for (let i = 0; i < projection.dates.length; i++) {
      const t = toTime(projection.dates[i])
      // The projection starts at today, which the history already covers.
      if (t <= lastTime) continue
      data.push({ date: projection.dates[i], t, Projected: projection.total[i] ?? 0 })
    }
  }

  return data
}
