import { format } from "date-fns"

export function formatDate(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value
  if (Number.isNaN(d.getTime())) return "—"
  return format(d, "d MMM yyyy")
}

export function daysAgoLabel(days: number): string {
  if (days === 0) return "today"
  if (days === 1) return "1 day ago"
  return `${days} days ago`
}

/** "just now", "5 min ago", "3 h ago", "2 days ago" for a UTC timestamp. A timestamp with no
 *  zone (the backend stores UTC without one) is read as UTC, not local time. */
export function timeAgo(value: string, from: Date = new Date()): string {
  const utc = /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(value) ? `${value}Z` : value
  const minutes = Math.floor((from.getTime() - new Date(utc).getTime()) / 60_000)
  if (Number.isNaN(minutes)) return "—"
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return daysAgoLabel(Math.floor(hours / 24))
}

/** Whole calendar days from `value` (a date or UTC timestamp) to `from`, never negative. */
export function daysSince(value: string, from: Date = new Date()): number | null {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  const start = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const end = new Date(from.getFullYear(), from.getMonth(), from.getDate())
  return Math.max(0, Math.round((end.getTime() - start.getTime()) / 86_400_000))
}

export function todayIso(): string {
  return format(new Date(), "yyyy-MM-dd")
}

export type ChartRange = "1W" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "5Y" | "All"

export const CHART_RANGES: ChartRange[] = ["1W", "1M", "3M", "6M", "YTD", "1Y", "5Y", "All"]

/** docs/05-ui.md "Overview" range row. `null` means no lower bound ("All"). */
export function rangeStartDate(range: ChartRange, from: Date = new Date()): Date | null {
  const d = new Date(from)
  switch (range) {
    case "1W":
      d.setDate(d.getDate() - 7)
      return d
    case "1M":
      d.setMonth(d.getMonth() - 1)
      return d
    case "3M":
      d.setMonth(d.getMonth() - 3)
      return d
    case "6M":
      d.setMonth(d.getMonth() - 6)
      return d
    case "YTD":
      return new Date(d.getFullYear(), 0, 1)
    case "1Y":
      d.setFullYear(d.getFullYear() - 1)
      return d
    case "5Y":
      d.setFullYear(d.getFullYear() - 5)
      return d
    case "All":
      return null
  }
}

/** A start date early enough to fetch an account's whole history. */
export const ALL_HISTORY_FROM = "1900-01-01"

export function rangeStartIso(range: ChartRange, from: Date = new Date()): string | undefined {
  const start = rangeStartDate(range, from)
  return start ? format(start, "yyyy-MM-dd") : undefined
}
