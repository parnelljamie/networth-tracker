import { useState } from "react"
import { DailyMovers } from "@/components/DailyMovers"
import { HistoryProjectionControls } from "@/components/HistoryProjectionControls"
import { ALL_HISTORY_FROM, rangeStartIso, type ChartRange } from "@/lib/dates"
import { Link } from "react-router"
import { useAccountHistories, useAccounts, type AccountSummary } from "@/api/hooks/useAccounts"
import { useHoldingsForAccounts } from "@/api/hooks/useHoldings"
import { useProjection } from "@/api/hooks/useProjection"
import { useAllowances } from "@/api/hooks/useRecurring"
import { AccountFormDialog } from "@/components/AccountFormDialog"
import { AllowanceMeters } from "@/components/AllowanceMeters"
import { CurrentVsProjectedChart } from "@/components/charts/CurrentVsProjectedChart"
import { DeltaChip } from "@/components/DeltaChip"
import { EmptyState } from "@/components/EmptyState"
import { type HorizonYears } from "@/components/HorizonToggle"
import { Money } from "@/components/Money"
import { PageHeader } from "@/components/PageHeader"
import { Pct } from "@/components/Pct"
import { PersonAvatar } from "@/components/PersonAvatar"
import { StalenessBadge } from "@/components/StalenessBadge"
import { StatTile } from "@/components/StatTile"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Plus } from "lucide-react"
import { WRAPPER_LABELS } from "@/lib/categories"
import { formatUnits } from "@/lib/format"
import { projectedEndValue, sumHistories, sumProjectionAccounts } from "@/lib/series"

const INVESTMENT_COLOR = "var(--chart-1, #2a78d6)"

/** Wrapper display order for the grouped account cards (ISA first — it's the one with an
 *  allowance people actively manage), then anything unexpected, alphabetically. */
const WRAPPER_ORDER = ["isa", "lisa", "jisa", "gia", "none"]

export function Investments() {
  const { data: accounts } = useAccounts({ category: "investment" })
  const { data: allowances } = useAllowances()
  const [horizon, setHorizon] = useState<HorizonYears>(20)
  const [range, setRange] = useState<ChartRange>("All")
  const [showProjection, setShowProjection] = useState(true)
  const [addOpen, setAddOpen] = useState(false)

  const investmentAccounts = accounts ?? []
  const accountIds = investmentAccounts.map((a) => a.id)

  const { data: projection } = useProjection({ months: horizon * 12, byAccount: true })
  // "All" has no range start, so ask for everything rather than the server's one-year default.
  const histories = useAccountHistories(accountIds, rangeStartIso(range) ?? ALL_HISTORY_FROM)
  const holdingsAccountIds = investmentAccounts
    .filter((a) => a.valuation_method === "holdings")
    .map((a) => a.id)
  const holdingsQueries = useHoldingsForAccounts(holdingsAccountIds)

  if (!accounts) return null

  if (investmentAccounts.length === 0) {
    return (
      <div className="flex flex-col gap-10">
        <PageHeader eyebrow="Every investment account" title="Investments" />
        <EmptyState
          title="No investments yet"
          description="Add an ISA or general investment account to track holdings, gains and your ISA allowance."
          action={
            <Button size="sm" onClick={() => setAddOpen(true)}>
              Add investment account
            </Button>
          }
        />
        <AccountFormDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          dialogTitle="Add investment account"
          defaultCategory="investment"
          defaultWrapper="isa"
        />
      </div>
    )
  }

  const total = investmentAccounts.reduce((sum, a) => sum + a.scoped_value_gbp, 0)
  const totalGain = investmentAccounts.reduce((sum, a) => sum + (a.gain_gbp ?? 0), 0)
  const totalCost = investmentAccounts.reduce((sum, a) => sum + (a.cost_basis_gbp ?? 0), 0)
  const dayChange = investmentAccounts.reduce((sum, a) => sum + (a.day_change_gbp ?? 0), 0)

  const history = sumHistories(histories.map((q) => q.data ?? []).filter((h) => h.length > 0))
  const projectionValues = sumProjectionAccounts(
    projection?.by_account,
    accountIds,
    projection?.dates.length ?? 0
  )
  const projectedTotal = projectionValues[projectionValues.length - 1]

  // Group by wrapper (docs/05-ui.md: ISA is a wrapper, not a category — this is the "ISA view").
  const byWrapper = new Map<string, AccountSummary[]>()
  for (const account of investmentAccounts) {
    const list = byWrapper.get(account.wrapper) ?? []
    list.push(account)
    byWrapper.set(account.wrapper, list)
  }
  const wrappers = Array.from(byWrapper.keys()).sort((a, b) => {
    const ai = WRAPPER_ORDER.indexOf(a)
    const bi = WRAPPER_ORDER.indexOf(b)
    return (ai < 0 ? WRAPPER_ORDER.length : ai) - (bi < 0 ? WRAPPER_ORDER.length : bi) || a.localeCompare(b)
  })

  // Combined holdings across every investment account — the same instrument held in an ISA and a
  // GIA is one row here (the Person page's combined-holdings logic, widened to the household).
  const combined = new Map<
    number,
    { symbol: string; name: string; units: number; value_gbp: number; day_change_gbp: number }
  >()
  for (const query of holdingsQueries) {
    for (const pos of query.data?.positions ?? []) {
      const existing = combined.get(pos.instrument.id)
      if (existing) {
        existing.units += pos.units
        existing.value_gbp += pos.value_gbp
        existing.day_change_gbp += pos.day_change_gbp
      } else {
        combined.set(pos.instrument.id, {
          symbol: pos.instrument.symbol,
          name: pos.instrument.name,
          units: pos.units,
          value_gbp: pos.value_gbp,
          day_change_gbp: pos.day_change_gbp,
        })
      }
    }
  }

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow="Every investment account"
        title="Investments"
        actions={
          <Button variant="outline" onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" />
            Add investment account
          </Button>
        }
      />

      <section className="grid grid-cols-2 gap-x-8 gap-y-6 lg:grid-cols-4" aria-label="Summary">
        <StatTile label="Household investments" value={<Money value={total} whole />} hint={`${investmentAccounts.length} account${investmentAccounts.length === 1 ? "" : "s"}`} />
        <StatTile
          label="Gain"
          value={<Money value={totalGain} whole />}
          hint={<DeltaChip amountGbp={totalGain} pct={totalCost > 0 ? totalGain / totalCost : undefined} className="text-xs" />}
        />
        <StatTile label="Today" value={<Money value={dayChange} />} hint={<DeltaChip amountGbp={dayChange} className="text-xs" />} />
        <StatTile label={`In ${horizon} years`} value={<Money value={projectedTotal ?? 0} whole />} hint="At each account’s expected return" />
      </section>

      <section aria-label="Investment value chart">
          <CurrentVsProjectedChart
            historyDates={history.dates}
            historyValues={history.values}
            projectionDates={projection?.dates ?? []}
            projectionValues={projectionValues}
            label="Investment value"
            color={INVESTMENT_COLOR}
            historyFrom={rangeStartIso(range)}
            showProjection={showProjection}
            headerActions={
              <HistoryProjectionControls
                range={range}
                onRangeChange={setRange}
                showProjection={showProjection}
                onShowProjectionChange={setShowProjection}
                horizon={horizon}
                onHorizonChange={setHorizon}
              />
            }
          />
      </section>

      <div className="grid grid-cols-1 gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-10">
          {wrappers.map((wrapper) => {
            const rows = byWrapper.get(wrapper) ?? []
            const wrapperTotal = rows.reduce((sum, a) => sum + a.scoped_value_gbp, 0)
            return (
              <Card key={wrapper}>
                <CardHeader>
                  <CardTitle>{WRAPPER_LABELS[wrapper] ?? wrapper}</CardTitle>
                  <CardAction>
                    <Money value={wrapperTotal} whole className="font-heading text-[22px] text-ink" />
                  </CardAction>
                </CardHeader>
                <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {rows.map((account) => {
                    const projected = projectedEndValue(projection?.by_account, account.id)
                    return (
                      <Link key={account.id} to={`/accounts/${account.id}`} className="group/acct">
                        <Card variant="boxed" className="h-full transition-colors group-hover/acct:border-ink-muted">
                          <CardContent className="flex flex-col gap-2.5">
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <p className="truncate text-[15px] font-medium text-ink">{account.name}</p>
                                {account.provider && <p className="truncate text-xs text-ink-muted">{account.provider}</p>}
                              </div>
                              <div className="flex -space-x-1.5">
                                {account.owners.map((o) => (
                                  <PersonAvatar key={o.person_id} name={o.name} color={o.color} className="ring-2 ring-card" />
                                ))}
                              </div>
                            </div>
                            <div className="flex flex-wrap items-baseline gap-x-3">
                              <Money value={account.scoped_value_gbp} display whole className="text-[30px] leading-tight text-ink" />
                              {account.gain_gbp !== null && account.gain_gbp !== undefined && (
                                <DeltaChip amountGbp={account.gain_gbp} pct={account.gain_pct ?? undefined} className="text-xs" />
                              )}
                            </div>
                            <p className="text-xs text-ink-muted">
                              {projected === undefined ? "No projection" : <><Money value={projected} compact /> in {horizon} years</>}
                            </p>
                            {account.staleness !== "ok" && (
                              <StalenessBadge
                                staleness={account.staleness as "ok" | "warn" | "alert"}
                                daysSince={account.days_since_update ?? null}
                                prices={account.valuation_method === "holdings"}
                              />
                            )}
                          </CardContent>
                        </Card>
                      </Link>
                    )
                  })}
                </CardContent>
              </Card>
            )
          })}
        </div>

        <div className="flex flex-col gap-10">
          <Card>
            <CardHeader>
              <CardTitle>ISA allowance</CardTitle>
            </CardHeader>
            <CardContent>
              <AllowanceMeters
                allowances={allowances}
                kind="isa"
                showRemaining
                emptyNote="No people with an ISA allowance yet."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Today&apos;s movers</CardTitle>
            </CardHeader>
            <CardContent>
              <DailyMovers
                movers={Array.from(combined, ([id, h]) => {
                  const previous = h.value_gbp - h.day_change_gbp
                  return {
                    key: id,
                    symbol: h.symbol,
                    name: h.name,
                    dayChangeGbp: h.day_change_gbp,
                    dayChangePct: previous ? h.day_change_gbp / previous : null,
                  }
                })
                  .sort((a, b) => Math.abs(b.dayChangeGbp) - Math.abs(a.dayChangeGbp))
                  .slice(0, 8)}
                emptyNote="No holdings to show yet."
              />
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Combined holdings</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {combined.size === 0 ? (
            <p className="text-sm text-ink-muted">
              No holdings yet — accounts tracked by holdings show their positions here.
            </p>
          ) : (
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-ink text-xs text-ink-muted">
                  <th className="py-2 pr-3 text-left font-medium">Instrument</th>
                  <th className="py-2 pr-3 text-right font-medium">Units</th>
                  <th className="py-2 pr-3 text-right font-medium">Value</th>
                  <th className="py-2 text-right font-medium">Weight</th>
                </tr>
              </thead>
              <tbody>
                {Array.from(combined.values())
                  .sort((a, b) => b.value_gbp - a.value_gbp)
                  .map((row) => (
                    <tr key={row.symbol} className="border-b border-rule-soft">
                      <td className="py-2.5 pr-3">
                        <span className="text-ink">{row.name}</span>
                        <span className="ml-2.5 font-mono-figures text-xs text-ink-2">{row.symbol}</span>
                      </td>
                      <td className="py-2.5 pr-3 text-right tabular-nums text-ink-2">{formatUnits(row.units)}</td>
                      <td className="py-2.5 pr-3 text-right">
                        <Money value={row.value_gbp} className="text-ink" />
                      </td>
                      <td className="py-2.5 text-right text-ink-2">
                        <Pct value={total ? row.value_gbp / total : 0} decimals={1} />
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <AccountFormDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        dialogTitle="Add investment account"
        defaultCategory="investment"
        defaultWrapper="isa"
      />
    </div>
  )
}
