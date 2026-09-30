import { useSchedule, type ScheduleRowOut } from "@/api/hooks/useLoans"
import { formatDate } from "@/lib/dates"

export const PROPERTY_COLOR = "var(--chart-4, #eda100)"

export const DEBT_COLOR = "var(--chart-5, #e87ba4)"

type ScheduleSummary = NonNullable<ReturnType<typeof useSchedule>["data"]>["summary"]

export function fixEndsHint(summary: ScheduleSummary | undefined): string | undefined {
  const period = summary?.current_period
  if (!period || period.days_left === null || period.days_left === undefined) return undefined
  const years = Math.floor(period.days_left / 365)
  const months = Math.floor((period.days_left % 365) / 30)
  const endLabel = period.end_date ? ` (${formatDate(period.end_date)})` : ""
  return `Fix ends in ${years}y ${months}m${endLabel}`
}

/** One point per calendar year (last row seen), so a decades-long schedule stays a light chart
 *  series rather than plotting every monthly payment. `rows` is already date-ascending. */
export function yearlySampled(rows: ScheduleRowOut[]): { date: string; balance: number }[] {
  const byYear = new Map<number, ScheduleRowOut>()
  for (const row of rows) {
    byYear.set(new Date(row.date).getFullYear(), row)
  }
  return Array.from(byYear.values()).map((r) => ({ date: r.date, balance: r.closing_balance }))
}

/**
 * One history point per calendar month. Recharts spaces a category axis by index, not by time, so
 * mixing a multi-year *daily* history with a yearly future would squeeze three decades of forecast
 * into the last few pixels. Thinning history to months keeps both halves legible (and the Table
 * readable) without changing the shape of either line.
 */
export function monthlySampled(dates: string[], values: number[]): { dates: string[]; values: number[] } {
  const lastIndexOfMonth = new Map<string, number>()
  dates.forEach((d, i) => lastIndexOfMonth.set(d.slice(0, 7), i))
  const indexes = Array.from(lastIndexOfMonth.values()).sort((a, b) => a - b)
  return { dates: indexes.map((i) => dates[i]), values: indexes.map((i) => values[i]) }
}

/** The same one-point-per-year thinning for the projection's monthly `dates`/values pair. */
export function yearlySampledSeries(dates: string[], values: number[]): Map<string, number> {
  const byYear = new Map<number, { date: string; value: number }>()
  dates.forEach((date, i) => {
    const value = values[i]
    if (value === undefined) return
    byYear.set(new Date(date).getFullYear(), { date, value })
  })
  return new Map(Array.from(byYear.values()).map((p) => [p.date, p.value]))
}

export function scheduleRowsToCsv(rows: ScheduleRowOut[]): string {
  const header = "Date,Rate,Opening balance,Payment,Interest,Principal,Overpayment,Closing balance"
  const lines = rows.map((r) =>
    [r.date, r.annual_rate, r.opening_balance, r.payment, r.interest, r.principal, r.overpayment, r.closing_balance].join(",")
  )
  return [header, ...lines].join("\n")
}
