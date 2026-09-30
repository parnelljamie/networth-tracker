import { useState } from "react"
import { useAccountHistory } from "@/api/hooks/useAccounts"
import { AccountHistoryChart } from "@/components/charts/AccountHistoryChart"
import { ChartCard, type ChartCardSeries } from "@/components/charts/ChartCard"
import { RangeFilter } from "@/components/RangeFilter"
import { ALL_HISTORY_FROM, rangeStartIso, type ChartRange } from "@/lib/dates"

export function AccountHistoryTab({ accountId, isHoldings }: { accountId: number; isHoldings: boolean }) {
  const [range, setRange] = useState<ChartRange>("1Y")
  // "All" has no lower bound, but the endpoint defaults a missing date_from to the last 365 days,
  // so ask for everything explicitly - as pages/Investments.tsx and pages/Pensions.tsx do.
  const { data: history } = useAccountHistory(accountId, rangeStartIso(range) ?? ALL_HISTORY_FROM)

  const dates = (history ?? []).map((row) => row.date)
  const value = (history ?? []).map((row) => row.value_gbp)
  const netContributions = (history ?? []).map((row) => row.net_contributions_gbp ?? null)
  const hasContributions = isHoldings && netContributions.some((v) => v !== null)

  const series: ChartCardSeries[] = [{ key: "value", label: "Value", color: "var(--ink)", values: value }]
  if (hasContributions) {
    series.push({
      key: "net_contributions",
      label: "Net contributions",
      color: "var(--ink-muted)",
      values: netContributions.map((v) => v ?? 0),
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <RangeFilter value={range} onChange={setRange} />
      </div>
      <ChartCard dates={dates} series={series}>
        <AccountHistoryChart
          dates={dates}
          value={value}
          netContributions={hasContributions ? netContributions : undefined}
        />
      </ChartCard>
    </div>
  )
}
