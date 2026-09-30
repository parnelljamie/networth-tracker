import { formatDelta } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"
import { cn } from "@/lib/utils"

interface DeltaChipProps {
  amountGbp: number
  pct?: number
  className?: string
}

const COLOR_BY_DIRECTION = {
  up: "text-gain",
  down: "text-loss",
  flat: "text-ink-muted",
} as const

export function DeltaChip({ amountGbp, pct, className }: DeltaChipProps) {
  const privacy = usePrivacyMode()
  const { direction, text } = formatDelta(amountGbp, pct)
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-sm whitespace-nowrap tabular-nums",
        COLOR_BY_DIRECTION[direction],
        className
      )}
    >
      {privacy ? "•••" : text}
    </span>
  )
}
