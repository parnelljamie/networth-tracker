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
import { formatDate, formatTime } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"

interface AccountHistoryChartProps {
  dates: string[]
  value: number[]
  netContributions?: (number | null)[]
  height?: number
  /** Scale the value axis to the data instead of starting it at zero, so day-to-day moves
   *  show (the Live page). The default keeps zero in view, which is honest for long histories. */
  fitToData?: boolean
  /** `dates` are timestamps within one day (the 1D charts): label them by clock time. */
  intraday?: boolean
  /** A level to mark with a dashed line, kept in view: the previous close on a 1D chart. */
  baseline?: number
  /** What the line is called in the tooltip. */
  label?: string
}

function TooltipContent({ active, payload, label, intraday }: any) {
  const privacy = usePrivacyMode()
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border p-2 text-xs shadow-sm" style={{ background: "var(--surface)" }}>
      <p className="mb-1 text-ink-muted">{intraday ? formatTime(label) : formatDate(label)}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-ink">
          <span className="size-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="flex-1">{p.name}</span>
          <span className="tabular-nums">{privacy ? "•••" : formatGBP(p.value)}</span>
        </p>
      ))}
    </div>
  )
}

export function AccountHistoryChart({
  dates,
  value,
  netContributions,
  height = 260,
  fitToData = false,
  intraday = false,
  baseline,
  label = "Value",
}: AccountHistoryChartProps) {
  const privacy = usePrivacyMode()
  const hasContributions = netContributions?.some((v) => v !== null && v !== undefined)

  const data = dates.map((d, i) => ({
    date: d,
    Value: value[i] ?? 0,
    ...(hasContributions ? { "Net contributions": netContributions?.[i] ?? null } : {}),
  }))

  if (dates.length === 0) {
    return <p className="py-16 text-center text-sm text-ink-muted">No history yet.</p>
  }

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={(d) => (intraday ? formatTime(d) : formatDate(d))}
            stroke="var(--axis)"
            tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            stroke="var(--axis)"
            tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
            tickFormatter={(v) => (privacy ? "•••" : formatGBP(v, { compact: true }))}
            width={64}
            domain={
              baseline !== undefined
                ? [(min: number) => Math.min(min, baseline), (max: number) => Math.max(max, baseline)]
                : fitToData
                  ? ["auto", "auto"]
                  : undefined
            }
          />
          {!fitToData && <ReferenceLine y={0} stroke="var(--axis)" />}
          {baseline !== undefined && <ReferenceLine y={baseline} stroke="var(--ink-muted)" strokeDasharray="4 4" />}
          <Tooltip content={<TooltipContent intraday={intraday} />} />
          <Line type="monotone" dataKey="Value" name={label} stroke="var(--ink)" strokeWidth={2} dot={false} isAnimationActive={false} />
          {hasContributions && (
            <Line
              type="monotone"
              dataKey="Net contributions"
              stroke="var(--ink-muted)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
