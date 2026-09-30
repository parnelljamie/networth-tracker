import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"
import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"
import { formatGBP } from "@/lib/format"

export interface DonutSegment {
  key: string
  label: string
  value: number
  color: string
}

interface DonutChartProps {
  segments: DonutSegment[]
  /** Round legend and tooltip figures to whole pounds (Overview's Allocation card). */
  whole?: boolean
}

const MAX_SEGMENTS = 6

function foldToTopN(segments: DonutSegment[], n: number): DonutSegment[] {
  const sorted = [...segments].sort((a, b) => b.value - a.value)
  if (sorted.length <= n) return sorted
  const head = sorted.slice(0, n - 1)
  const tailValue = sorted.slice(n - 1).reduce((sum, s) => sum + s.value, 0)
  return [...head, { key: "other", label: "Other", value: tailValue, color: "var(--ink-muted)" }]
}

export function DonutChart({ segments, whole }: DonutChartProps) {
  const data = foldToTopN(
    segments.filter((s) => s.value > 0),
    MAX_SEGMENTS
  )
  const total = data.reduce((sum, s) => sum + s.value, 0)

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-muted">No assets yet.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="mx-auto h-[160px] w-[160px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius={48}
              outerRadius={72}
              paddingAngle={1}
              stroke="var(--surface)"
              strokeWidth={2}
            >
              {data.map((segment) => (
                <Cell key={segment.key} fill={segment.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value) => formatGBP(Number(value), { whole })}
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex flex-1 flex-col gap-1.5">
        {data.map((segment) => (
          <li key={segment.key} className="flex items-center gap-2 text-sm">
            <span
              className="size-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: segment.color }}
              aria-hidden="true"
            />
            <span className="flex-1 truncate text-ink">{segment.label}</span>
            <Money value={segment.value} whole={whole} className="shrink-0 text-ink-2" />
            <Pct value={total > 0 ? segment.value / total : 0} decimals={0} className="w-10 shrink-0 text-right text-ink-muted" />
          </li>
        ))}
      </ul>
    </div>
  )
}
