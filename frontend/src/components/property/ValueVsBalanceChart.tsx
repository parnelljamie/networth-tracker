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
import type { ScheduleRowOut } from "@/api/hooks/useLoans"
import { ChartCard, type ChartCardSeries } from "@/components/charts/ChartCard"
import { formatDate } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"
import {
  PROPERTY_COLOR,
  DEBT_COLOR,
  yearlySampled,
  monthlySampled,
  yearlySampledSeries,
} from "@/lib/property"

export function ValueVsBalanceChart({
  propertyDates,
  propertyValues,
  loanDates,
  loanValues,
  futureLoanRows,
  projectionDates,
  projectedPropertyValues,
}: {
  propertyDates: string[]
  propertyValues: number[]
  loanDates: string[]
  loanValues: number[]
  /** Full future amortisation schedule (today onwards) for the linked loan, if any. */
  futureLoanRows?: ScheduleRowOut[]
  /** `GET /api/projection?by_account=true` dates, and this property's series aligned to them. */
  projectionDates?: string[]
  projectedPropertyValues?: number[]
}) {
  const privacy = usePrivacyMode()
  const property = monthlySampled(propertyDates, propertyValues)
  const loan = monthlySampled(loanDates, loanValues)
  const allDates = Array.from(new Set([...property.dates, ...loan.dates])).sort()

  if (allDates.length === 0) {
    return <p className="py-16 text-center text-sm text-ink-muted">No history yet.</p>
  }

  const propertyByDate = new Map(property.dates.map((d, i) => [d, property.values[i]]))
  const loanByDate = new Map(loan.dates.map((d, i) => [d, loan.values[i]]))
  const historyEnd = allDates[allDates.length - 1]
  const latestPropertyValue = propertyByDate.get(historyEnd) ?? property.values[property.values.length - 1] ?? 0
  const latestLoanValue = loanByDate.get(historyEnd) ?? loan.values[loan.values.length - 1] ?? 0

  // docs/05-ui.md "Property & Mortgage" chart spec: "history solid, future dashed". The loan's
  // future comes from its real amortisation schedule (already fetched for the Schedule card
  // below). The property's future comes from `GET /api/projection?by_account=true`, which applies
  // the account's growth model server-side — the same plumbing the Pensions and Investments pages
  // use, so the growth maths lives in one place rather than being re-implemented here.
  const futurePoints = yearlySampled((futureLoanRows ?? []).filter((r) => r.date > historyEnd))
  const projectedProperty = yearlySampledSeries(
    projectionDates ?? [],
    projectedPropertyValues ?? []
  )
  const futureDates = [
    ...futurePoints.map((p) => p.date),
    ...Array.from(projectedProperty.keys()),
  ].filter((d) => d > historyEnd)
  const timelineDates = Array.from(new Set([...allDates, ...futureDates])).sort()

  const data = timelineDates.map((d) => {
    const isHistory = d <= historyEnd
    const futureLoanBalance = futurePoints.find((p) => p.date === d)?.balance
    // Until the projection loads, the dashed line stays anchored at the latest known value
    // rather than vanishing.
    const projectedValue = projectedProperty.get(d) ?? (projectedProperty.size === 0 ? latestPropertyValue : null)
    return {
      date: d,
      "Property value": isHistory ? propertyByDate.get(d) ?? null : null,
      "Property value (projected)":
        d === historyEnd ? latestPropertyValue : !isHistory ? projectedValue : null,
      "Mortgage balance": isHistory ? loanByDate.get(d) ?? null : null,
      "Mortgage balance (projected)":
        d === historyEnd ? latestLoanValue : !isHistory ? (futureLoanBalance ?? null) : null,
    }
  })

  // docs/05-ui.md chart rules: every chart gets a Table toggle — ChartCard supplies the legend
  // (swatch + label) and the toggle; values are forward-filled onto the combined date axis so
  // the table has a figure for both series on every row (history where it exists, projection
  // beyond it).
  function forwardFill(byDate: Map<string, number>): number[] {
    let last = 0
    const out: number[] = []
    for (const d of timelineDates) {
      last = byDate.get(d) ?? last
      out.push(last)
    }
    return out
  }
  const propertyWithFuture = new Map([...propertyByDate, ...projectedProperty])
  const loanWithFuture = new Map([
    ...loanByDate,
    ...futurePoints.map((p) => [p.date, p.balance] as const),
  ])
  const cardSeries: ChartCardSeries[] = [
    { key: "property", label: "Property value", color: PROPERTY_COLOR, values: forwardFill(propertyWithFuture) },
    { key: "loan", label: "Mortgage balance", color: DEBT_COLOR, values: forwardFill(loanWithFuture) },
  ]

  return (
    <ChartCard dates={timelineDates} series={cardSeries}>
      <div style={{ height: 280 }}>
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
            <Tooltip
              formatter={(value) => (privacy ? "•••" : formatGBP(Number(value ?? 0)))}
              labelFormatter={(label) => formatDate(label as string)}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", fontSize: 12 }}
            />
            <Line type="monotone" dataKey="Property value" stroke={PROPERTY_COLOR} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line
              type="monotone"
              dataKey="Property value (projected)"
              stroke={PROPERTY_COLOR}
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
              connectNulls
              isAnimationActive={false}
              legendType="none"
            />
            <Line type="monotone" dataKey="Mortgage balance" stroke={DEBT_COLOR} strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
            <Line
              type="monotone"
              dataKey="Mortgage balance (projected)"
              stroke={DEBT_COLOR}
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
