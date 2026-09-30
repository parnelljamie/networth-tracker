import { formatPct } from "@/lib/format"
import { cn } from "@/lib/utils"

interface PctProps {
  value: number
  decimals?: number
  className?: string
}

export function Pct({ value, decimals, className }: PctProps) {
  return (
    <span className={cn("tabular-nums", className)}>
      {formatPct(value, decimals)}
    </span>
  )
}
