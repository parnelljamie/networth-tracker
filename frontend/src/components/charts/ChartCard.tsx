import { useState } from "react"
import type { ReactNode } from "react"
import { Money } from "@/components/Money"
import { formatDate } from "@/lib/dates"
import { cn } from "@/lib/utils"

export interface ChartCardSeries {
  key: string
  label: string
  color: string
  values: number[]
}

export interface LegendItem {
  key: string
  label: string
  color: string
  /** "line" draws a short stroke instead of a dot, e.g. for a total or projection line. */
  shape?: "dot" | "line" | "dashed"
  /** Shown dimmed and struck through when the caller has hidden it from the plot. */
  hidden?: boolean
}

interface ChartCardProps {
  dates: string[]
  series: ChartCardSeries[]
  /** Shown next to the swatch legend row, e.g. a Category|Total toggle. */
  headerActions?: ReactNode
  /** Suppress the built-in swatch legend when the caller already renders an equivalent one
   *  (e.g. Projections' scenario comparison, whose checkboxes double as the legend). The Table
   *  toggle is always shown regardless — every chart rule still applies. */
  hideLegend?: boolean
  /** Replaces the legend built from `series`, for charts that draw lines not in the table. */
  legend?: LegendItem[]
  /** Makes legend entries clickable, e.g. to show/hide that series. */
  onLegendClick?: (key: string) => void
  children: ReactNode
}

/** docs/05-ui.md "Chart rules": legend with a swatch, and a Table toggle showing the same data. */
export function ChartCard({ dates, series, headerActions, hideLegend, legend, onLegendClick, children }: ChartCardProps) {
  const [showTable, setShowTable] = useState(false)
  const legendItems: LegendItem[] = legend ?? series.map((s) => ({ key: s.key, label: s.label, color: s.color }))

  const legendRow =
    !hideLegend && (legend ? legendItems.length > 0 : series.length >= 2) ? (
      <ul className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
        {legendItems.map((s) => (
          <li key={s.key}>
            <LegendEntryWrapper onClick={onLegendClick ? () => onLegendClick(s.key) : undefined} hidden={s.hidden}>
              {s.shape === "line" || s.shape === "dashed" ? (
                <span
                  className="w-[18px] shrink-0 border-t-2"
                  style={{ borderColor: s.color, borderTopStyle: s.shape === "dashed" ? "dashed" : "solid" }}
                />
              ) : (
                <span className="size-2.5 shrink-0 rounded-[2px]" style={{ backgroundColor: s.color }} />
              )}
              <span className={cn("text-ink-2", s.hidden && "line-through")}>{s.label}</span>
            </LegendEntryWrapper>
          </li>
        ))}
      </ul>
    ) : (
      <span />
    )

  return (
    <div className="flex flex-col gap-3">
      {headerActions && <div className="flex flex-wrap items-center justify-end gap-2">{headerActions}</div>}

      {showTable ? (
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink text-left text-xs text-ink-muted">
                <th className="py-2 font-medium">Date</th>
                {series.map((s) => (
                  <th key={s.key} className="py-2 text-right font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dates
                .map((d, i) => ({ d, i }))
                .reverse()
                .map(({ d, i }) => (
                  <tr key={d} className="border-b border-rule-soft">
                    <td className="py-1.5 text-ink-2">{formatDate(d)}</td>
                    {series.map((s) => (
                      <td key={s.key} className="py-1.5 text-right">
                        <Money value={s.values[i] ?? 0} />
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
          {dates.length === 0 && <p className="py-4 text-center text-sm text-ink-muted">No history yet.</p>}
        </div>
      ) : (
        children
      )}

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {legendRow}
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          className="py-1 text-xs text-primary underline underline-offset-2 hover:text-ink"
        >
          {showTable ? "View as chart" : "View as table"}
        </button>
      </div>
    </div>
  )
}

function LegendEntryWrapper({
  onClick,
  hidden,
  children,
}: {
  onClick?: () => void
  hidden?: boolean
  children: ReactNode
}) {
  const className = cn("flex items-center gap-1.5", hidden && "opacity-40")
  if (!onClick) return <span className={className}>{children}</span>
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={!hidden}
      title={hidden ? "Show on chart" : "Hide from chart"}
      className={cn(className, "rounded hover:bg-muted")}
    >
      {children}
    </button>
  )
}
