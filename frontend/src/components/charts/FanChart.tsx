import { Area, ComposedChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { timeTicks, valueAxis } from "@/lib/chartData"
import { formatDate } from "@/lib/dates"
import type { FanRow } from "@/lib/fan"
import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"
import { useTimeTickCount } from "@/lib/responsive"

function TooltipContent({ active, payload }: { active?: boolean; payload?: { payload: FanRow }[] }) {
  const privacy = usePrivacyMode()
  const row = payload?.[0]?.payload
  if (!active || !row) return null
  const money = (v: number) => (privacy ? "•••" : formatGBP(v, { compact: true }))
  const lines: [string, number][] = [
    ["90th percentile", row.outer[1]],
    ["75th percentile", row.inner[1]],
    ["Median", row.median],
    ["25th percentile", row.inner[0]],
    ["10th percentile", row.outer[0]],
    ["Projection", row.plan],
  ]
  return (
    <div className="rounded-lg border border-border p-2 text-xs shadow-sm" style={{ background: "var(--surface)" }}>
      <p className="mb-1 text-ink-muted">{formatDate(row.date)}</p>
      {lines.map(([label, value]) => (
        <p key={label} className="flex items-center justify-between gap-4 text-ink">
          <span>{label}</span>
          <span className="tabular-nums">{money(value)}</span>
        </p>
      ))}
    </div>
  )
}

/** docs/03-domain-logic.md §10: the spread of simulated outcomes around the projection. */
export function FanChart({ rows, height = 300 }: { rows: FanRow[]; height?: number }) {
  const privacy = usePrivacyMode()
  const tickCount = useTimeTickCount()
  if (rows.length === 0) {
    return <p className="py-16 text-center text-sm text-ink-muted">Nothing to project yet.</p>
  }
  const start = rows[0].t
  const end = rows[rows.length - 1].t
  const { domain, ticks } = valueAxis(
    rows.map((r) => ({ date: r.date, t: r.t, low: r.outer[0], high: r.outer[1], plan: r.plan })),
    ["low", "high", "plan"],
    false
  )

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={[start, end]}
            ticks={timeTicks(start, end, tickCount)}
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
            domain={domain}
            ticks={ticks}
            allowDataOverflow
          />
          <Tooltip content={<TooltipContent />} />
          <Area
            type="monotone"
            dataKey="outer"
            stroke="none"
            fill="var(--accent)"
            fillOpacity={0.12}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="inner"
            stroke="none"
            fill="var(--accent)"
            fillOpacity={0.2}
            isAnimationActive={false}
          />
          <Line type="monotone" dataKey="median" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line
            type="monotone"
            dataKey="plan"
            stroke="var(--ink)"
            strokeWidth={2}
            strokeDasharray="4 4"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
