import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { formatDate } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"
import { useTimeTickCount } from "@/lib/responsive"
import { cn } from "@/lib/utils"
import type { ChartCardSeries } from "@/components/charts/ChartCard"
import {
  MS_PER_YEAR,
  type AgePrecision,
  ageAt,
  buildChartRows,
  pointCount,
  timeTicks,
  toTime,
  valueAxis,
} from "@/lib/chartData"

interface AreaStackChartProps {
  dates: string[]
  series: ChartCardSeries[]
  total: number[]
  /** "categories": stacked area per series (assets above zero, debts below) + total line.
   *  "total": total only. docs/05-ui.md "toggle Categories | Total". */
  mode?: "categories" | "total"
  height?: number
  /** docs/05-ui.md "Show projection" toggle: extends the total as a dashed line beyond `dates`.
   *  The first projection date should be `dates[dates.length - 1]` (today) so the dashed
   *  segment starts exactly where the solid line ends. */
  projection?: { dates: string[]; total: number[] }
  /** Vertical hairline markers (docs/05-ui.md Projections "milestone markers"). */
  milestones?: { date: string; label: string }[]
  /** Extra axis rows under the dates showing each person's age at the same tick positions. */
  /** Stack the category areas (default true). When false each category is its own line at its
   *  own value, so none of them coincide with the Total line. */
  stacked?: boolean
  /** Draw the solid Total line (default true). */
  showTotal?: boolean
  ageRows?: { key: string | number; label: string; dateOfBirth: string; color?: string | null }[]
}

// Plot area insets, matching the chart margin and Y-axis width below, so age labels line up
// with the date ticks.
const PLOT_LEFT_PX = 8 + 64
const PLOT_RIGHT_PX = 8

function TooltipContent({ active, payload, label }: any) {
  const privacy = usePrivacyMode()
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface p-2 text-xs shadow-sm" style={{ background: "var(--surface)" }}>
      <p className="mb-1 text-ink-muted">{formatDate(new Date(label))}</p>
      {payload
        .slice()
        .reverse()
        .map((p: any) => (
          <p key={p.dataKey} className="flex items-center gap-2 text-ink">
            <span className="size-2 rounded-full" style={{ backgroundColor: p.color }} />
            <span className="flex-1">{p.name}</span>
            <span className="tabular-nums">{privacy ? "•••" : formatGBP(p.value)}</span>
          </p>
        ))}
    </div>
  )
}

export function AreaStackChart({
  dates,
  series,
  total,
  mode = "categories",
  height = 280,
  projection,
  milestones,
  showTotal = true,
  stacked = true,
  ageRows,
}: AreaStackChartProps) {
  const privacy = usePrivacyMode()
  const tickCount = useTimeTickCount()

  const data = buildChartRows(dates, series, total, projection)

  if (dates.length === 0) {
    return <p className="py-16 text-center text-sm text-ink-muted">No history yet.</p>
  }

  const startTime = data[0].t as number
  const endTime = data[data.length - 1].t as number

  const ticks = timeTicks(startTime, endTime, tickCount)
  const { domain: yDomain, ticks: yTicks } = valueAxis(data, [
    ...(showTotal ? ["Total"] : []),
    ...(projection ? ["Projected"] : []),
    ...(mode === "categories" ? series.map((s) => s.label) : []),
  ], stacked && mode === "categories")
  const spanYears = (endTime - startTime) / MS_PER_YEAR
  // Whole years once the range is long enough for them to differ across the ticks; below that
  // they would all read the same, so fall back to years and months.
  const agePrecision: AgePrecision = spanYears >= 4 ? "years" : "months"

  return (
    <div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={[startTime, endTime]}
              ticks={ticks}
              tickFormatter={(t: number) => formatDate(new Date(t))}
              stroke="var(--axis)"
              tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
              minTickGap={40}
            />
            <YAxis
              stroke="var(--axis)"
              tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
              tickFormatter={(v) => (privacy ? "•••" : formatGBP(v, { compact: true }))}
              width={64}
              domain={yDomain}
              ticks={yTicks}
              allowDataOverflow
            />
            <ReferenceLine y={0} stroke="var(--axis)" />
            {milestones?.map((m) => (
              <ReferenceLine
                key={`${m.date}-${m.label}`}
                x={toTime(m.date)}
                stroke="var(--axis)"
                strokeDasharray="3 3"
                label={{ value: m.label, position: "top", fill: "var(--ink-muted)", fontSize: 10 }}
              />
            ))}
            <Tooltip content={<TooltipContent />} />
            {mode === "categories" &&
              series.map((s) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.label}
                  stackId={stacked ? "stack" : undefined}
                  stroke={s.color}
                  fill={s.color}
                  fillOpacity={stacked ? 0.1 : 0.04}
                  strokeWidth={2}
                  // A series with a single point (e.g. an account added today) draws no line, so
                  // mark it with a dot instead.
                  dot={pointCount(data, s.label) === 1 ? { r: 5, fill: s.color, fillOpacity: 1, strokeWidth: 0, clipDot: false } : false}
                  isAnimationActive={false}
                />
              ))}
            {showTotal && (
              <Line
                type="monotone"
                dataKey="Total"
                stroke="var(--ink)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            )}
            {projection && (
              <Line
                type="monotone"
                dataKey="Projected"
                name="Projected"
                stroke="var(--ink)"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {ageRows?.map((row) => (
        <div key={row.key} className="relative mt-1 h-4 text-[11px] text-ink-muted">
          <span
            className="absolute top-0 left-0 truncate pr-2 text-right"
            style={{ width: PLOT_LEFT_PX, color: row.color ?? undefined }}
          >
            {row.label}
          </span>
          <div className="absolute inset-y-0" style={{ left: PLOT_LEFT_PX, right: PLOT_RIGHT_PX }}>
            {ticks.map((t, i) => (
              <span
                key={t}
                // Centred under each date tick, except the ends, which would spill past the plot.
                className={cn(
                  // nowrap: the end labels are pinned to the plot edges with nothing to grow
                  // into, so "31y 0m" would otherwise break across two lines.
                  "absolute top-0 whitespace-nowrap tabular-nums",
                  i === 0 ? "" : i === ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2"
                )}
                style={{ left: `${endTime > startTime ? ((t - startTime) / (endTime - startTime)) * 100 : 0}%` }}
              >
                {ageAt(row.dateOfBirth, t, agePrecision)}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
