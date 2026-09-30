import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"

export interface BalanceSegment {
  key: string
  label: string
  value: number
  color: string
}

interface BalanceSheetBarProps {
  assets: BalanceSegment[]
  /** Total owed, as a positive number. */
  owed: number
  owedColor: string
}

/**
 * Overview's balance sheet: what the household owns, split by category, over what it owes,
 * drawn to the same scale so the gap between the bars is the net worth.
 */
export function BalanceSheetBar({ assets, owed, owedColor }: BalanceSheetBarProps) {
  const shown = assets.filter((a) => a.value > 0)
  const owned = shown.reduce((sum, a) => sum + a.value, 0)
  if (owned <= 0 && owed <= 0) return <p className="text-sm text-ink-muted">No assets yet.</p>
  const scale = Math.max(owned, owed)

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-3 md:gap-4">
        <span className="w-10 shrink-0 text-[13px] text-ink-2 md:w-16">Own</span>
        <div className="flex h-5 min-w-0 flex-1">
          <div
            className="flex h-5 gap-0.5 overflow-hidden rounded-r"
            style={{ width: `${(owned / scale) * 100}%` }}
            role="img"
            aria-label="What you own, by category"
          >
            {shown.map((a) => (
              <div
                key={a.key}
                className="h-5 min-w-0.5"
                style={{ flexGrow: a.value, flexBasis: 0, backgroundColor: a.color }}
                title={a.label}
              />
            ))}
          </div>
        </div>
        <Money value={owned} whole className="w-24 shrink-0 text-right font-heading text-lg text-ink md:w-28 md:text-xl" />
      </div>
      <div className="flex items-center gap-3 md:gap-4">
        <span className="w-10 shrink-0 text-[13px] text-ink-2 md:w-16">Owe</span>
        <div className="flex h-5 min-w-0 flex-1">
          {owed > 0 && (
            <div
              className="h-5 rounded-r"
              style={{ width: `${(owed / scale) * 100}%`, backgroundColor: owedColor }}
              role="img"
              aria-label="What you owe"
            />
          )}
        </div>
        <Money value={-owed} whole className="w-24 shrink-0 text-right font-heading text-lg text-ink md:w-28 md:text-xl" />
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-7 gap-y-2 md:pl-20">
        {[...shown, ...(owed > 0 ? [{ key: "owed", label: "Owed", value: -owed, color: owedColor }] : [])].map((a) => (
          <li key={a.key} className="flex items-center gap-2 text-[13px] text-ink-2">
            <span className="size-2.5 shrink-0 rounded-[2px]" style={{ backgroundColor: a.color }} aria-hidden="true" />
            <span className="text-ink">{a.label}</span>
            <Money value={a.value} whole />
            <span className="text-ink-muted">
              <Pct value={owned ? Math.abs(a.value) / owned : 0} decimals={0} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
