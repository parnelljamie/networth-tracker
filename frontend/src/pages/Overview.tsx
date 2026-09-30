import { useState } from "react"
import { DailyMovers } from "@/components/DailyMovers"
import { Link, useNavigate } from "react-router"
import { useAccounts } from "@/api/hooks/useAccounts"
import { useNetWorthCurrent, useNetWorthHistory } from "@/api/hooks/useNetworth"
import { usePeople } from "@/api/hooks/usePeople"
import { useProjection } from "@/api/hooks/useProjection"
import { useAllowances, useUpcomingPlans } from "@/api/hooks/useRecurring"
import { AllowanceMeters } from "@/components/AllowanceMeters"
import { AttributionCard } from "@/components/AttributionCard"
import { BalanceSheetBar } from "@/components/BalanceSheetBar"
import { DepositProtectionCard } from "@/components/DepositProtectionCard"
import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"
import { Button } from "@/components/ui/button"
import { AreaStackChart } from "@/components/charts/AreaStackChart"
import { ChartCard, type ChartCardSeries, type LegendItem } from "@/components/charts/ChartCard"
import { DeltaChip } from "@/components/DeltaChip"
import { EmptyState } from "@/components/EmptyState"
import { PersonAvatar } from "@/components/PersonAvatar"
import { RangeFilter } from "@/components/RangeFilter"
import { Segmented } from "@/components/Segmented"
import { StalenessBadge } from "@/components/StalenessBadge"
import { StatTile } from "@/components/StatTile"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { openAddAccount } from "@/lib/appDialogs"
import {
  CATEGORY_COLORS,
  CATEGORY_GROUP_ORDER,
  CATEGORY_LABELS,
  LIABILITY_CATEGORIES,
  type Category,
} from "@/lib/categories"
import { rangeStartIso, type ChartRange } from "@/lib/dates"
import { regroupByCategory } from "@/lib/series"
import { useTheme } from "@/lib/theme"

const MIN_PROJECTION_YEARS = 1
const MAX_PROJECTION_YEARS = 30

/** How the hero describes the range-change figure ("▲ £62,380 over the year"). */
const RANGE_WORDS: Record<ChartRange, string> = {
  "1W": "over the week",
  "1M": "over the month",
  "3M": "over three months",
  "6M": "over six months",
  YTD: "this year so far",
  "1Y": "over the year",
  "5Y": "over five years",
  All: "since you started",
}

function formatShortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
}

function formatMonthYear(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" })
}

export function Overview() {
  const navigate = useNavigate()
  const [scope, setScope] = useState<number | null>(null)
  const [range, setRange] = useState<ChartRange>("1Y")
  const [chartMode, setChartMode] = useState<"categories" | "total">("categories")
  const [showProjection, setShowProjection] = useState(false)
  const { data: people } = usePeople()
  const { data: networth, isLoading } = useNetWorthCurrent(scope ?? undefined)
  const { data: accounts } = useAccounts()
  const { data: allowances } = useAllowances()
  const { data: upcoming } = useUpcomingPlans({ days: 60 })
  const theme = useTheme()

  // "Show projection" toggle (docs/05-ui.md Overview #1): extends the total as a dashed line
  // for 12 months, base scenario.
  const [projectionYears, setProjectionYears] = useState(1)
  const { data: projection } = useProjection({
    personId: scope ?? undefined,
    months: projectionYears * 12,
  })
  const { data: fullProjection } = useProjection({ personId: scope ?? undefined, months: 360 })

  const granularity = range === "5Y" || range === "All" ? "week" : "day"
  const [view, setView] = useState<"total" | "liquid">("total")
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set())
  const { data: totalHistory } = useNetWorthHistory({
    personId: scope ?? undefined,
    dateFrom: rangeStartIso(range),
    granularity,
    groupBy: "category",
  })
  // The liquid view sums only accounts marked liquid, so it needs per-account history.
  const { data: accountHistory } = useNetWorthHistory({
    personId: scope ?? undefined,
    dateFrom: rangeStartIso(range),
    granularity,
    groupBy: "account",
  })
  // docs/05-ui.md Overview #2 wants a one-month change per person. group_by=person already
  // weights each account by that person's share, so the series key is the person id.
  const { data: personMonthHistory } = useNetWorthHistory({
    dateFrom: rangeStartIso("1M"),
    granularity: "day",
    groupBy: "person",
  })
  const personMonthChange = new Map<number, { abs: number; pct: number | undefined }>()
  for (const s of personMonthHistory?.series ?? []) {
    if (s.values.length === 0) continue
    const first = s.values[0]
    const abs = s.values[s.values.length - 1] - first
    personMonthChange.set(Number(s.key), { abs, pct: first ? abs / Math.abs(first) : undefined })
  }

  const liquidAccounts = (networth?.accounts ?? []).filter((a) => a.is_liquid)
  const history = view === "liquid" ? regroupByCategory(accountHistory, liquidAccounts) : totalHistory
  const headlineValue = view === "liquid" ? (networth?.liquid_gbp ?? 0) : (networth?.total_gbp ?? 0)
  const liquidDayChange = liquidAccounts.reduce((sum, a) => sum + (a.day_change_gbp ?? 0), 0)
  const dayChange =
    view === "liquid"
      ? { abs: liquidDayChange, pct: headlineValue - liquidDayChange ? liquidDayChange / (headlineValue - liquidDayChange) : undefined }
      : networth?.changes.day.abs_gbp !== null && networth?.changes.day.abs_gbp !== undefined
        ? { abs: networth.changes.day.abs_gbp, pct: networth.changes.day.pct ?? undefined }
        : null

  const hasAccounts = (accounts?.length ?? 0) > 0

  if (!isLoading && !hasAccounts) {
    return (
      <EmptyState
        title="Welcome to Waymark"
        description="Start by adding people, then your first accounts — an ISA and a mortgage are the usual places to begin."
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button variant="outline" onClick={() => navigate("/settings")}>
              Add people
            </Button>
            <Button
              variant="outline"
              onClick={() => openAddAccount({ category: "investment", wrapper: "isa" })}
            >
              Add your ISA
            </Button>
            <Button
              variant="outline"
              onClick={() => openAddAccount({ category: "mortgage", wrapper: "none" })}
            >
              Add your mortgage
            </Button>
          </div>
        }
      />
    )
  }

  // The mortgage is folded into property so the chart shows home equity rather than a separate
  // debt band below zero; the stack still sums to the total line.
  const rawSeries = history?.series ?? []
  const mortgageValues = rawSeries.find((s) => s.key === "mortgage")?.values
  const hasProperty = rawSeries.some((s) => s.key === "property")
  const historySeries = rawSeries
    .filter((s) => !(hasProperty && s.key === "mortgage"))
    .map((s): ChartCardSeries => {
      const foldMortgage = s.key === "property" && mortgageValues !== undefined
      return {
        key: s.key,
        label: foldMortgage ? "Property equity" : (CATEGORY_LABELS[s.key as Category] ?? s.label),
        color: CATEGORY_COLORS[s.key as Category]?.[theme] ?? "var(--ink-muted)",
        values: foldMortgage ? s.values.map((v, i) => v + (mortgageValues[i] ?? 0)) : s.values,
      }
    })

  // Legend clicks hide series from the plot and the y-axis rescales to what is still drawn. The
  // Total line always stays the real total; hide it too to zoom in on the remaining categories.
  function toggleHidden(key: string) {
    setHiddenKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }
  const visibleSeries = historySeries.filter((s) => !hiddenKeys.has(s.key))
  const projectionAvailable = showProjection && !!projection && view === "total"

  const categoryValue = (category: string) =>
    networth?.by_category.find((c) => c.category === category)?.value_gbp ?? 0
  const mortgageOwed = Math.abs(categoryValue("mortgage"))
  const propertyValue = categoryValue("property")
  const mortgageLtv = mortgageOwed > 0 && propertyValue > 0 ? mortgageOwed / propertyValue : null

  // Balance sheet: gross assets by category over everything owed, drawn to one scale.
  const balanceAssets = (networth?.by_category ?? [])
    .filter((c) => !LIABILITY_CATEGORIES.includes(c.category as Category))
    .map((c) => ({
      key: c.category,
      label: CATEGORY_LABELS[c.category as Category] ?? c.category,
      value: c.value_gbp,
      color: CATEGORY_COLORS[c.category as Category]?.[theme] ?? "var(--ink-muted)",
    }))
  const owedTotal = (networth?.by_category ?? [])
    .filter((c) => LIABILITY_CATEGORIES.includes(c.category as Category))
    .reduce((sum, c) => sum + Math.abs(c.value_gbp), 0)

  const accountsByCategory = new Map<string, typeof accounts>()
  for (const account of accounts ?? []) {
    const list = accountsByCategory.get(account.category) ?? []
    list.push(account)
    accountsByCategory.set(account.category, list)
  }

  const scopeName = scope ? people?.find((p) => p.id === scope)?.name : null
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
  const rangeChange =
    history && history.total.length > 0 && networth
      ? {
          abs: headlineValue - history.total[0],
          pct: history.total[0] ? (headlineValue - history.total[0]) / Math.abs(history.total[0]) : undefined,
        }
      : null

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <section className="flex flex-wrap items-end justify-between gap-x-10 gap-y-6">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span className="eyebrow">
            {today} · {scopeName ?? "Household"}
          </span>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
            <h1 className="font-heading text-2xl text-ink-2 md:text-[30px]">
              {scopeName ? `${scopeName} is worth` : "Together you’re worth"}
            </h1>
            <Segmented
              label="Net worth view"
              options={[
                { value: "total", label: "Total" },
                { value: "liquid", label: "Liquid" },
              ]}
              value={view}
              onChange={setView}
              size="sm"
            />
          </div>
          <p className="text-[64px] leading-none font-medium tracking-[-0.03em] text-ink md:text-[104px]">
            <Money value={headlineValue} display whole />
          </p>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-7 gap-y-1">
            {dayChange && (
              <span className="flex items-baseline gap-2 text-[15px]">
                <DeltaChip amountGbp={dayChange.abs} pct={dayChange.pct} className="text-[15px]" />
                <span className="text-ink-muted">today</span>
              </span>
            )}
            {rangeChange && (
              <span className="flex items-baseline gap-2 text-[15px]">
                <DeltaChip amountGbp={rangeChange.abs} pct={rangeChange.pct} className="text-[15px]" />
                <span className="text-ink-muted">{RANGE_WORDS[range]}</span>
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-start gap-3.5 md:items-end">
          <Segmented
            label="Scope"
            options={[{ value: null, label: "Household" }, ...(people ?? []).map((p) => ({ value: p.id, label: p.name }))]}
            value={scope}
            onChange={setScope}
          />
          <RangeFilter value={range} onChange={setRange} />
        </div>
      </section>

      <section aria-label="Net worth chart">
        <ChartCard
          dates={history?.dates ?? []}
          series={historySeries}
          legend={[
            ...(chartMode === "categories"
              ? historySeries.map(
                  (s): LegendItem => ({ key: s.key, label: s.label, color: s.color, hidden: hiddenKeys.has(s.key) })
                )
              : []),
            { key: "total", label: "Net worth", color: "var(--ink)", shape: "line", hidden: hiddenKeys.has("total") },
            ...(projectionAvailable
              ? [
                  {
                    key: "projected",
                    label: "Projection, base scenario",
                    color: "var(--ink)",
                    shape: "dashed",
                    hidden: hiddenKeys.has("projected"),
                  } as LegendItem,
                ]
              : []),
          ]}
          onLegendClick={toggleHidden}
          headerActions={
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[13px]">
              <Segmented
                label="Chart view"
                options={[
                  { value: "categories", label: "Categories" },
                  { value: "total", label: "Total" },
                ]}
                value={chartMode}
                onChange={setChartMode}
                size="sm"
              />
              {view === "total" && (
                <>
                  <label className="flex items-center gap-2 text-ink-2">
                    <input
                      type="checkbox"
                      className="size-4 accent-(--accent)"
                      checked={showProjection}
                      onChange={(e) => setShowProjection(e.target.checked)}
                    />
                    Show projection
                  </label>
                  <label className="flex items-center gap-1.5 text-ink-2">
                    <input
                      type="number"
                      min={MIN_PROJECTION_YEARS}
                      max={MAX_PROJECTION_YEARS}
                      step={1}
                      value={projectionYears}
                      onChange={(e) => {
                        const years = Math.round(Number(e.target.value))
                        if (Number.isFinite(years) && years > 0) {
                          setProjectionYears(Math.min(MAX_PROJECTION_YEARS, Math.max(MIN_PROJECTION_YEARS, years)))
                        }
                      }}
                      aria-label="Projection length in years"
                      className="h-8 w-14 rounded-md border border-border bg-card px-2 text-right tabular-nums text-ink"
                    />
                    {projectionYears === 1 ? "yr" : "yrs"}
                  </label>
                </>
              )}
            </div>
          }
        >
          <AreaStackChart
            dates={history?.dates ?? []}
            total={history?.total ?? []}
            showTotal={!hiddenKeys.has("total")}
            stacked={false}
            mode={chartMode}
            ageRows={(people ?? [])
              .filter((p) => p.date_of_birth && (scope === null || p.id === scope))
              .map((p) => ({
                key: p.id,
                label: `${p.name} age`,
                dateOfBirth: p.date_of_birth!,
                color: p.color,
              }))}
            series={visibleSeries}
            projection={
              projectionAvailable && !hiddenKeys.has("projected") && projection
                ? { dates: projection.dates, total: projection.total }
                : undefined
            }
          />
        </ChartCard>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Balance sheet</CardTitle>
        </CardHeader>
        <CardContent>
          <BalanceSheetBar
            assets={balanceAssets}
            owed={owedTotal}
            owedColor={CATEGORY_COLORS.mortgage[theme]}
          />
        </CardContent>
      </Card>

      <section className="grid grid-cols-2 gap-x-8 gap-y-6 lg:grid-cols-4" aria-label="Liquidity and debt">
        <StatTile label="Accessible now" value={<Money value={networth?.liquid_gbp ?? 0} whole />} hint="Cash and investments you can sell" />
        <StatTile label="Locked" value={<Money value={networth?.illiquid_gbp ?? 0} whole />} hint="Pensions, home equity and LISAs" />
        <StatTile label="Total debt" value={<Money value={Math.abs(networth?.liabilities_gbp ?? 0)} whole />} hint="Mortgage, loans and cards" />
        <StatTile
          label="Mortgage LTV"
          value={mortgageLtv === null ? "—" : <Pct value={mortgageLtv} decimals={1} />}
          hint={mortgageLtv === null ? "No mortgage or property" : "Mortgage owed ÷ property value"}
        />
      </section>

      <div className="grid grid-cols-1 gap-x-12 gap-y-10 md:grid-cols-2 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="md:col-span-2 xl:col-span-1">
          <CardHeader>
            <CardTitle>Accounts</CardTitle>
            <CardAction>
              <button type="button" className="text-[13px] font-medium text-primary hover:underline" onClick={() => openAddAccount()}>
                Add account
              </button>
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-col">
            {CATEGORY_GROUP_ORDER.filter((c) => accountsByCategory.has(c)).map((category) => {
              const rows = accountsByCategory.get(category) ?? []
              const subtotal = rows.reduce((sum, a) => sum + a.scoped_value_gbp, 0)
              return (
                <div key={category}>
                  <div className="flex items-baseline gap-2.5 border-b border-border pt-4 pb-2">
                    <span
                      className="size-2 shrink-0 self-center rounded-[2px]"
                      style={{ backgroundColor: CATEGORY_COLORS[category]?.[theme] ?? "var(--ink-muted)" }}
                      aria-hidden="true"
                    />
                    <span className="flex-1 font-heading text-[19px] text-ink italic">{CATEGORY_LABELS[category]}</span>
                    <Money value={subtotal} whole className="font-heading text-[19px] text-ink" />
                  </div>
                  {rows.map((account) => (
                    <Link
                      key={account.id}
                      to={`/accounts/${account.id}`}
                      className="flex min-h-12 items-center gap-3 border-b border-rule-soft py-2 pl-4 text-sm transition-colors hover:bg-muted/60"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-ink">{account.name}</p>
                        <div className="flex min-w-0 items-center gap-2 text-xs text-ink-muted">
                          {account.provider && <span className="truncate">{account.provider}</span>}
                          {account.staleness !== "ok" && (
                            <StalenessBadge
                              staleness={account.staleness as "ok" | "warn" | "alert"}
                              daysSince={account.days_since_update ?? null}
                              prices={account.valuation_method === "holdings"}
                            />
                          )}
                        </div>
                      </div>
                      <div className="flex -space-x-1.5">
                        {account.owners.map((o) => (
                          <PersonAvatar key={o.person_id} name={o.name} color={o.color} size="sm" className="ring-2 ring-background" />
                        ))}
                      </div>
                      <Money value={account.scoped_value_gbp} whole className="w-24 text-right text-ink" />
                    </Link>
                  ))}
                </div>
              )
            })}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-10">
          <Card>
            <CardHeader>
              <CardTitle>People</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col">
              {(networth?.by_person ?? []).map((person) => {
                const pct = networth?.total_gbp ? person.value_gbp / networth.total_gbp : 0
                const month = personMonthChange.get(person.person_id)
                return (
                  <Link
                    key={person.person_id}
                    to={`/people/${person.person_id}`}
                    className="flex flex-col gap-2.5 border-b border-rule-soft py-3.5 transition-colors hover:bg-muted/60"
                  >
                    <div className="flex items-center gap-3">
                      <PersonAvatar name={person.name} color={person.color} className="size-9" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-ink">{person.name}</p>
                        {month && (
                          <p className="flex flex-wrap items-baseline gap-x-1 text-xs text-ink-muted">
                            <DeltaChip amountGbp={month.abs} pct={month.pct} className="text-xs" /> this month
                          </p>
                        )}
                      </div>
                      <div className="flex flex-col items-end">
                        <Money value={person.value_gbp} whole className="font-heading text-2xl text-ink" />
                        <span className="text-xs text-ink-muted">
                          <Pct value={pct} decimals={1} /> of household
                        </span>
                      </div>
                    </div>
                    <div className="h-1 rounded-full bg-rule-soft">
                      <div
                        className="h-1 rounded-full bg-ink-muted"
                        style={{ width: `${Math.max(0, Math.min(100, pct * 100))}%` }}
                      />
                    </div>
                  </Link>
                )
              })}
              {(!people || people.length === 0) && <p className="text-sm text-ink-muted">Add people in Settings.</p>}
              {(networth?.by_person ?? []).length > 0 && (
                <p className="pt-2.5 text-xs text-ink-muted">Joint accounts are split by each owner’s share.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Allowances</CardTitle>
            </CardHeader>
            <CardContent>
              <AllowanceMeters allowances={allowances} kind="isa" showPensionLine whole />
            </CardContent>
          </Card>

          <AttributionCard personId={scope ?? undefined} />
        </div>

        <div className="flex flex-col gap-10">
          <Card>
            <CardHeader>
              <CardTitle>Coming up</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col">
              {(networth?.freshness.stale_accounts ?? []).map((acc) => (
                <div key={`stale-${acc.account_id}`} className="flex items-baseline gap-3.5 border-b border-rule-soft py-2.5 text-sm">
                  <span className="w-14 shrink-0 font-mono-figures text-xs text-warn">Due</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-ink">Update {acc.name}</p>
                    <p className="text-xs text-ink-muted">{acc.days_since} days old</p>
                  </div>
                </div>
              ))}
              {(upcoming ?? []).slice(0, 8).map((item, i) => (
                <div key={`${item.plan_id}-${item.date}-${i}`} className="flex items-baseline gap-3.5 border-b border-rule-soft py-2.5 text-sm">
                  <span className="w-14 shrink-0 font-mono-figures text-xs text-ink">{formatShortDate(item.date)}</span>
                  <span className="min-w-0 flex-1 truncate text-ink">{item.name}</span>
                  <Money value={item.gross_amount_gbp} className="text-ink" />
                </div>
              ))}
              {(upcoming ?? []).length === 0 && (networth?.freshness.stale_accounts ?? []).length === 0 && (
                <p className="text-sm text-ink-muted">Nothing due in the next 60 days.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Milestones</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col">
              {(fullProjection?.milestones ?? []).slice(0, 3).map((m, i) => (
                <div key={`${m.kind}-${m.date}-${i}`} className="flex items-baseline gap-4 border-b border-rule-soft py-2.5 last:border-b-0">
                  <span className="w-24 shrink-0 font-heading text-[17px] text-brass italic">{formatMonthYear(m.date)}</span>
                  <span className="min-w-0 flex-1 text-sm text-ink">{m.label}</span>
                </div>
              ))}
              {(fullProjection?.milestones ?? []).length === 0 && (
                <p className="text-sm text-ink-muted">No projected milestones yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Today&apos;s movers</CardTitle>
            </CardHeader>
            <CardContent>
              <DailyMovers
                movers={(networth?.top_movers ?? []).map((m) => ({
                  key: String(m.instrument_id),
                  symbol: String(m.symbol),
                  name: String(m.name),
                  dayChangeGbp: Number(m.day_change_gbp),
                  dayChangePct: m.day_change_pct == null ? null : Number(m.day_change_pct),
                }))}
              />
            </CardContent>
          </Card>

          <DepositProtectionCard />
        </div>
      </div>
    </div>
  )
}
