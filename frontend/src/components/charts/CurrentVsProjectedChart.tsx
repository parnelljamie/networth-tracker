import type { ReactNode } from "react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { ChartCard, type ChartCardSeries } from "@/components/charts/ChartCard"
import { formatDate } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"
import { useTimeTickCount } from "@/lib/responsive"

interface CurrentVsProjectedChartProps {
  /** Historical points, date-ascending. May be empty (a fresh install has no history yet). */
  historyDates: string[]
  historyValues: number[]
  /** Projected points from today forwards, date-ascending. */
  projectionDates: string[]
  projectionValues: number[]
  label: string
  color: string
  headerActions?: ReactNode
  /** ISO date; history before it is left off so the chart zooms to the chosen range. */
  historyFrom?: string
  /** Hide the dashed projection entirely. Defaults to shown. */
  showProjection?: boolean
}

function toTime(iso: string): number {
  return new Date(iso).getTime()
}

/** A round tick step (1, 2, 2.5 or 5 × a power of ten) close to `rough`. */
function niceStep(rough: number): number {
  if (!(rough > 0)) return 1
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const n = rough / magnitude
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10
  return nice * magnitude
}

/** Evenly spaced tick positions; recharts' own number ticks ignore dates. */
function timeTicks(start: number, end: number, count = 5): number[] {
  if (end <= start) return [start]
  const step = (end - start) / (count - 1)
  return Array.from({ length: count }, (_, i) => Math.round(start + step * i))
}

/**
 * The house current-vs-projected chart (docs/05-ui.md chart rules): **history solid, future
 * dashed**, same construction as the Property page's value-vs-balance chart — the two series are
 * one logical line, so the dashed series repeats the last historical point to join them up
 * without a visible gap.
 */
export function CurrentVsProjectedChart({
  historyDates,
  historyValues,
  projectionDates,
  projectionValues,
  label,
  color,
  headerActions,
  historyFrom,
  showProjection = true,
}: CurrentVsProjectedChartProps) {
  const privacy = usePrivacyMode()
  const tickCount = useTimeTickCount()

  if (historyFrom) {
    const start = historyDates.findIndex((d) => d >= historyFrom)
    historyDates = start === -1 ? [] : historyDates.slice(start)
    historyValues = start === -1 ? [] : historyValues.slice(start)
  }
  if (!showProjection) {
    projectionDates = []
    projectionValues = []
  }

  const historyByDate = new Map(historyDates.map((d, i) => [d, historyValues[i]]))
  const historyEnd = historyDates[historyDates.length - 1]
  const latestHistoryValue = historyValues[historyValues.length - 1]

  // Anything the projection reports at or before the last historical point is already covered by
  // the solid line, so only genuinely-future points become the dashed series.
  const futureIndexes = projectionDates
    .map((d, i) => ({ d, i }))
    .filter(({ d }) => historyEnd === undefined || d > historyEnd)
  const projectedByDate = new Map(futureIndexes.map(({ d, i }) => [d, projectionValues[i]]))

  const timelineDates = Array.from(
    new Set([...historyDates, ...futureIndexes.map(({ d }) => d)])
  ).sort()

  if (timelineDates.length === 0) {
    return <p className="py-16 text-center text-sm text-ink-muted">Nothing to project yet.</p>
  }

  const projectedKey = `${label} (projected)`
  const data = timelineDates.map((d) => {
    const isHistory = historyEnd !== undefined && d <= historyEnd
    return {
      date: d,
      t: toTime(d),
      [label]: isHistory ? (historyByDate.get(d) ?? null) : null,
      // Repeat the handover point so the dashed line starts exactly where the solid one ends.
      [projectedKey]:
        d === historyEnd ? (latestHistoryValue ?? null) : (projectedByDate.get(d) ?? null),
    }
  })

  // Forward-fill onto the combined axis so ChartCard's Table toggle has a figure on every row.
  function forwardFill(byDate: Map<string, number>): number[] {
    let last = 0
    const out: number[] = []
    for (const d of timelineDates) {
      last = byDate.get(d) ?? last
      out.push(last)
    }
    return out
  }
  const combined = new Map<string, number>([...historyByDate, ...projectedByDate])
  const cardSeries: ChartCardSeries[] = [
    { key: "value", label, color, values: forwardFill(combined) },
  ]

  // Fit the y-axis to what is on screen, with a little headroom, instead of always from £0 —
  // otherwise a week of movement on a large balance is a flat line.
  const visible = data
    .flatMap((row) => [row[label], row[projectedKey]])
    .filter((v): v is number => typeof v === "number")
  const lo = visible.length ? Math.min(...visible) : 0
  const hi = visible.length ? Math.max(...visible) : 0
  const pad = hi > lo ? (hi - lo) * 0.08 : Math.max(Math.abs(hi) * 0.02, 1)
  const step = niceStep((hi - lo + 2 * pad) / 4)
  let yMin = Math.floor((lo - pad) / step) * step
  if (lo >= 0 && yMin < 0) yMin = 0
  const yMax = Math.ceil((hi + pad) / step) * step
  const yDomain: [number, number] = [yMin, yMax]
  const yTicks = Array.from({ length: Math.round((yMax - yMin) / step) + 1 }, (_, i) => yMin + i * step)
  const startTime = data[0].t
  const endTime = data[data.length - 1].t

  return (
    <ChartCard dates={timelineDates} series={cardSeries} headerActions={headerActions}>
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={[startTime, endTime]}
              ticks={timeTicks(startTime, endTime, tickCount)}
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
            {yDomain[0] < 0 && yDomain[1] > 0 && <ReferenceLine y={0} stroke="var(--axis)" />}
            <Tooltip
              formatter={(value) => (privacy ? "•••" : formatGBP(Number(value ?? 0)))}
              labelFormatter={(t) => formatDate(new Date(t as number))}
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                fontSize: 12,
              }}
            />
            <Line
              type="monotone"
              dataKey={label}
              stroke={color}
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey={projectedKey}
              stroke={color}
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
              legendType="none"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}
