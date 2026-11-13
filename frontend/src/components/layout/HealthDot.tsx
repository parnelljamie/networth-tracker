import { TriangleAlert } from "lucide-react"
import { useHealth } from "@/api/hooks/useHealth"
import { usePricesStatus } from "@/api/hooks/useInstruments"
import { daysAgoLabel, minutesSince } from "@/lib/dates"

/** App-shell status pill: "● Live · 2m ago" / "▲ Prices 3 days old" per docs/05-ui.md. */
export function HealthDot() {
  const { data: health, isError } = useHealth()
  const { data: status } = usePricesStatus()
  const apiOk = Boolean(health) && !isError

  if (!apiOk) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-ink-muted">
        <span className="size-2 rounded-full bg-loss" aria-hidden="true" />
        Offline
      </span>
    )
  }

  if (status?.last_refresh_at) {
    const minutesAgo = minutesSince(status.last_refresh_at)
    const daysOld = Math.floor(minutesAgo / (60 * 24))
    if (daysOld >= 1) {
      return (
        <span className="flex items-center gap-1.5 text-xs text-warn">
          <TriangleAlert className="size-3.5" aria-hidden="true" />
          Prices {daysAgoLabel(daysOld)}
        </span>
      )
    }
    return (
      <span className="flex items-center gap-1.5 text-xs text-ink-muted">
        <span className="size-2 rounded-full bg-gain" aria-hidden="true" />
        {minutesAgo === 0 ? "Live · just now" : `Live · ${minutesAgo}m ago`}
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1.5 text-xs text-ink-muted">
      <span className="size-2 rounded-full bg-gain" aria-hidden="true" />
      Live
    </span>
  )
}
