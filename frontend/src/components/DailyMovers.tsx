import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"
import { cn } from "@/lib/utils"

export interface Mover {
  key: string | number
  symbol: string
  name: string
  dayChangeGbp: number
  dayChangePct: number | null | undefined
}

/** Holdings and how much each is up or down today: ruled rows (`list`) or a grid of tiles. */
export function DailyMovers({
  movers,
  emptyNote,
  variant = "list",
}: {
  movers: Mover[]
  emptyNote?: string
  variant?: "list" | "grid"
}) {
  if (movers.length === 0) {
    return <p className="text-sm text-ink-muted">{emptyNote ?? "No price moves yet today."}</p>
  }
  if (variant === "list") {
    return (
      <ul className="flex flex-col">
        {movers.map((m) => {
          const pct = m.dayChangePct ?? 0
          const tone = pct > 0.00005 ? "text-gain" : pct < -0.00005 ? "text-loss" : "text-ink-muted"
          return (
            <li key={m.key} className="flex min-w-0 items-baseline gap-3 border-b border-rule-soft py-2.5 last:border-b-0">
              <span className="w-14 shrink-0 truncate font-mono-figures text-xs text-ink" title={m.symbol}>
                {m.symbol}
              </span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink-2" title={m.name}>
                {m.name}
              </span>
              <span className={cn("shrink-0 text-[13px] whitespace-nowrap tabular-nums", tone)}>
                {pct > 0.00005 ? "▲ " : pct < -0.00005 ? "▼ " : ""}
                <Money value={Math.abs(m.dayChangeGbp)} /> <span className="text-xs">(<Pct value={Math.abs(pct)} decimals={2} />)</span>
              </span>
            </li>
          )
        })}
      </ul>
    )
  }
  return (
    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {movers.map((m) => {
        const pct = m.dayChangePct ?? 0
        const tone = pct > 0.00005 ? "text-gain" : pct < -0.00005 ? "text-loss" : "text-ink-muted"
        return (
          <li key={m.key} className="flex min-w-0 flex-col gap-0.5 rounded-lg border border-border bg-card px-3 py-2">
            <span className="truncate font-mono-figures text-xs text-ink-2" title={m.symbol}>
              {m.symbol}
            </span>
            <span className="truncate text-xs text-ink-muted" title={m.name}>
              {m.name}
            </span>
            <span className={cn("font-heading text-xl", tone)}>
              {pct > 0.00005 ? "▲ " : pct < -0.00005 ? "▼ " : ""}
              <Pct value={Math.abs(pct)} decimals={2} />
            </span>
            <Money value={m.dayChangeGbp} className={cn("text-xs", tone)} />
          </li>
        )
      })}
    </ul>
  )
}
