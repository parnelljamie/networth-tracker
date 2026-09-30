import { AlertTriangle, CircleAlert } from "lucide-react"
import { daysAgoLabel } from "@/lib/dates"
import { cn } from "@/lib/utils"

interface StalenessBadgeProps {
  staleness: "ok" | "warn" | "alert"
  daysSince: number | null
  /** The age is of market prices (holdings), not of a balance entry. */
  prices?: boolean
  /** Below `md`, show only the icon (the words stay for screen readers). */
  compactOnPhone?: boolean
  className?: string
}

export function StalenessBadge({ staleness, daysSince, prices = false, compactOnPhone = false, className }: StalenessBadgeProps) {
  if (staleness === "ok") {
    return (
      <span className={cn("text-ink-muted text-xs", className)}>
        <span className={cn(compactOnPhone && "hidden md:inline")}>
          {daysSince !== null ? `Updated ${daysAgoLabel(daysSince)}` : "—"}
        </span>
      </span>
    )
  }

  const Icon = staleness === "alert" ? CircleAlert : AlertTriangle
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs text-warn", className)}>
      <Icon className="size-3.5" aria-hidden="true" />
      <span className={cn(compactOnPhone && "sr-only md:not-sr-only")}>
        {staleLabel(daysSince, prices)}
      </span>
    </span>
  )
}

function staleLabel(daysSince: number | null, prices: boolean): string {
  if (prices) return daysSince !== null ? `Prices ${daysSince} days old` : "No price yet"
  return daysSince !== null ? `${daysSince} days old` : "Not updated yet"
}
