import type { AllowanceUsageOut } from "@/api/hooks/useRecurring"
import { Money } from "@/components/Money"

export type AllowanceKind = "isa" | "pension"

/** Meter colours follow docs/05-ui.md: ISA is chart slot 1 (blue) on a lighter step; the pension
 *  meter reuses the pension category colour (slot 2) the same way. */
const METER_STYLES: Record<AllowanceKind, { fill: string; track: string }> = {
  isa: { fill: "bg-[#2a78d6] dark:bg-[#3987e5]", track: "bg-[#cde2fb] dark:bg-[#184f95]" },
  pension: { fill: "bg-[#eb6834] dark:bg-[#d95926]", track: "bg-[#fbdccd] dark:bg-[#6b2c13]" },
}

interface AllowanceMetersProps {
  allowances: AllowanceUsageOut[] | undefined
  /** Which allowance the meter itself shows. */
  kind: AllowanceKind
  /** Also show the pension annual allowance as a secondary line (Overview's ISA card does). */
  showPensionLine?: boolean
  /** Show remaining alongside the tax year and days left. */
  showRemaining?: boolean
  /** Round figures to whole pounds (Overview's ISA card). */
  whole?: boolean
  emptyNote?: string
}

/**
 * One allowance meter per person — shared by Overview's "ISA allowance" card, the Investments
 * page's per-person ISA meters and the Pensions page's annual-allowance meters, so the three
 * cannot drift apart.
 */
export function AllowanceMeters({
  allowances,
  kind,
  showPensionLine,
  showRemaining,
  whole,
  emptyNote = "No ISA or pension accounts yet.",
}: AllowanceMetersProps) {
  if (!allowances || allowances.length === 0) {
    return <p className="text-sm text-ink-muted">{emptyNote}</p>
  }

  const styles = METER_STYLES[kind]

  return (
    <div className="flex flex-col gap-3">
      {allowances.map((row) => {
        const used = kind === "isa" ? row.isa_used : row.pension_used
        const limit = kind === "isa" ? row.isa_limit : row.pension_limit
        const remaining = kind === "isa" ? row.isa_remaining : row.pension_remaining
        const pctUsed = limit > 0 ? (used / limit) * 100 : 0
        return (
          <div key={row.person_id} className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink">{row.name}</span>
              <span className="text-ink-muted">
                <Money value={used} whole={whole} /> of <Money value={limit} whole={whole} />
              </span>
            </div>
            <div className={`h-2 rounded-full ${styles.track}`}>
              <div
                className={`h-2 rounded-full ${styles.fill}`}
                style={{ width: `${Math.max(0, Math.min(100, pctUsed))}%` }}
              />
            </div>
            <p className="text-xs text-ink-muted">
              {showRemaining ? (
                <>
                  <Money value={remaining} whole={whole} /> left ·{" "}
                </>
              ) : null}
              {row.tax_year} · {row.days_left} days left
              {row.is_estimated ? " · includes estimated contributions" : ""}
            </p>
            {showPensionLine && row.pension_limit > 0 && (
              <p className="text-xs text-ink-muted">
                Pension: <Money value={row.pension_used} whole={whole} /> of{" "}
                <Money value={row.pension_limit} whole={whole} />
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
