import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface StatTileProps {
  label: string
  value: ReactNode
  hint?: ReactNode
  className?: string
  /** Smaller figure for narrow cards, so full amounts fit instead of truncating. */
  compact?: boolean
}

export function StatTile({ label, value, hint, className, compact }: StatTileProps) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 border-t border-border pt-2.5", className)}>
      <span className="text-ink-2 text-[13px]">{label}</span>
      <span
        className={cn(
          "font-heading block leading-tight font-medium tracking-[-0.01em] text-ink break-words md:truncate",
          compact ? "text-2xl" : "text-[28px] sm:text-[32px]"
        )}
      >
        {value}
      </span>
      {hint ? <span className="text-ink-muted text-xs">{hint}</span> : null}
    </div>
  )
}
