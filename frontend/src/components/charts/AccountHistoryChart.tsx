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
import { formatDate } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"

interface AccountHistoryChartProps {
  dates: string[]
  value: number[]
  netContributions?: (number | null)[]
  height?: number
}

function TooltipContent({ active, payload, label }: any) {
  const privacy = usePrivacyMode()
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border p-2 text-xs shadow-sm" style={{ background: "var(--surface)" }}>
      <p className="mb-1 text-ink-muted">{formatDate(label)}</p>
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

export function AccountHistoryChart({ dates, value, netContributions, height = 260 }: AccountHistoryChartProps) {
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
            tickFormatter={(d) => formatDate(d)}
            stroke="var(--axis)"
            tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
            minTickGap={40}
          />
          <YAxis
            stroke="var(--axis)"
            tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
            tickFormatter={(v) => (privacy ? "•••" : formatGBP(v, { compact: true }))}
            width={64}
          />
          <ReferenceLine y={0} stroke="var(--axis)" />
          <Tooltip content={<TooltipContent />} />
          <Line type="monotone" dataKey="Value" stroke="var(--ink)" strokeWidth={2} dot={false} isAnimationActive={false} />
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
