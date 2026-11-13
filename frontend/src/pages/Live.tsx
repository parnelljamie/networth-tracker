import { useEffect, useState } from "react"
import { Link } from "react-router"
import { useAccountHistories, useAccounts } from "@/api/hooks/useAccounts"
import { useHoldingsForAccounts } from "@/api/hooks/useHoldings"
import { useInstrumentPrices, useIntraday, useTrading212Live } from "@/api/hooks/useLive"
import { useRole } from "@/api/hooks/useSync"
import { useTrading212Links } from "@/api/hooks/useTrading212"
import { AccountHistoryChart } from "@/components/charts/AccountHistoryChart"
import { DeltaChip } from "@/components/DeltaChip"
import { EmptyState } from "@/components/EmptyState"
import { Money } from "@/components/Money"
import { PageHeader } from "@/components/PageHeader"
import { RangeFilter } from "@/components/RangeFilter"
import { Segmented } from "@/components/Segmented"
import { Sparkline } from "@/components/Sparkline"
import { StatTile } from "@/components/StatTile"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ALL_HISTORY_FROM, formatDate, formatTime, rangeStartIso, todayIso, type ChartRange } from "@/lib/dates"
import { formatUnits } from "@/lib/format"
import { portfolioIntraday, withLiveNow } from "@/lib/intraday"
import { changePct, combineHoldings, periodReturn, sortHoldings, withLivePoint, type LiveSort } from "@/lib/live"
import { accountsInView, hasBothKinds, setLiveView, useLiveView, type LiveView } from "@/lib/liveView"
import { isMarketOpen, MARKETS } from "@/lib/markets"
import { openAddAccount } from "@/lib/appDialogs"
import { cn } from "@/lib/utils"

const RANGES: ChartRange[] = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "All"]

const RANGE_WORDS: Record<ChartRange, string> = {
  "1D": "today",
  "1W": "over the past week",
  "1M": "over the past month",
  "3M": "over 3 months",
  "6M": "over 6 months",
  YTD: "this year",
  "1Y": "over the past year",
  "5Y": "over 5 years",
  All: "since the start",
}

const VIEWS: { value: LiveView; label: string }[] = [
  { value: "all", label: "All" },
  { value: "investments", label: "Investments" },
  { value: "pensions", label: "Pensions" },
]

const EYEBROWS: Record<LiveView, string> = {
  all: "Stocks and shares, right now",
  investments: "Investment accounts, right now",
  pensions: "Pensions, right now",
}

const SORTS: { value: LiveSort; label: string }[] = [
  { value: "value", label: "Value" },
  { value: "today", label: "Today" },
  { value: "return", label: "Return" },
]

/** Re-renders on a timer, so "open / closed" follows the clock without reading it in render. */
function useNow(everyMs: number): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), everyMs)
    return () => window.clearInterval(id)
  }, [everyMs])
  return now
}

function MarketStrip() {
  const now = useNow(30_000)
  return (
    <ul className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ink-muted" title="From normal weekday hours; bank holidays aren't known">
      {MARKETS.map((market) => {
        const open = isMarketOpen(market, now)
        return (
          <li key={market.key} className="flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", open ? "bg-gain" : "bg-border")} aria-hidden="true" />
            {market.label} {open ? "open" : "closed"}
          </li>
        )
      })}
    </ul>
  )
}

/** docs/05-ui.md "Live": every holdings account as it stands now, the way a broker's app shows it. */
export function Live() {
  const { data: accounts } = useAccounts()
  const desktop = useRole() === "desktop"
  const [range, setRange] = useState<ChartRange>("1D")
  const now = useNow(60_000)
  const chosenView = useLiveView()
  const [sort, setSort] = useState<LiveSort>("value")
  const [sparkFrom] = useState(() => rangeStartIso("1M") ?? ALL_HISTORY_FROM)

  const everyHoldingsAccount = (accounts ?? []).filter((a) => a.valuation_method === "holdings")
  // Investments (what a broker's app shows) and pensions can be looked at apart.
  const { view, accounts: holdingsAccounts } = accountsInView(everyHoldingsAccount, chosenView)
  const canChooseView = hasBothKinds(everyHoldingsAccount)
  const accountIds = holdingsAccounts.map((a) => a.id)
  const holdingsQueries = useHoldingsForAccounts(accountIds)
  const histories = useAccountHistories(accountIds, (range === "1D" ? rangeStartIso("1W") : rangeStartIso(range)) ?? ALL_HISTORY_FROM)

  // Trading 212's own prices, while this page is open (PC only: the phone has no API key).
  const { data: links } = useTrading212Links(desktop)
  const live = useTrading212Live(desktop && (links?.length ?? 0) > 0)

  const loaded = holdingsQueries.filter((q) => q.data)
  const holdings = combineHoldings(
    holdingsQueries.flatMap((q, i) => (q.data ? [{ name: holdingsAccounts[i].name, positions: q.data.positions }] : []))
  )
  const sparklines = useInstrumentPrices(
    holdings.map((h) => h.instrumentId),
    sparkFrom
  )

  const intraday = useIntraday(
    holdings.map((h) => h.instrumentId),
    range === "1D"
  )

  if (!accounts) return null

  if (holdingsAccounts.length === 0) {
    return (
      <div className="flex flex-col gap-10">
        <PageHeader eyebrow="Stocks and shares, right now" title="Live" />
        <EmptyState
          title="No holdings to follow yet"
          description="Add an ISA, a general investment account or a pension tracked by its holdings, and its shares and funds show here with live prices."
          action={
            <Button size="sm" onClick={() => openAddAccount({ category: "investment", wrapper: "isa" })}>
              Add investment account
            </Button>
          }
        />
      </div>
    )
  }

  const cash = loaded.reduce((sum, q) => sum + (q.data?.cash_gbp ?? 0), 0)
  const invested = holdings.reduce((sum, h) => sum + h.valueGbp, 0)
  const cost = holdings.reduce((sum, h) => sum + h.costGbp, 0)
  const dayChange = holdings.reduce((sum, h) => sum + h.dayChangeGbp, 0)
  const total = invested + cash
  const gain = invested - cost

  const pricedAt = holdings
    .map((h) => h.priceAt)
    .filter((at): at is string => at !== null)
    .sort()
    .at(-1)
  const fromTrading212 = live.data?.some((r) => r.status === "ok" && r.priced > 0) ?? false
  const liveProblem = live.data?.find((r) => r.status === "error")
  const unsyncedTrade = live.data?.some((r) => r.units_differ) ?? false

  // History: the accounts' daily snapshots summed, ending at the live figure above.
  const historyRows = histories.map((q) => q.data ?? []).filter((h) => h.length > 0)
  const dates = Array.from(new Set(historyRows.flatMap((h) => h.map((p) => p.date)))).sort()
  const valueOn = dates.map(() => 0)
  const paidInOn: (number | null)[] = dates.map(() => 0)
  for (const history of historyRows) {
    const byDate = new Map(history.map((p) => [p.date, p]))
    let last: (typeof history)[number] | undefined
    dates.forEach((d, i) => {
      last = byDate.get(d) ?? last
      if (!last) return
      valueOn[i] += last.value_gbp
      const paid = last.net_contributions_gbp
      paidInOn[i] = paid == null || paidInOn[i] === null ? null : (paidInOn[i] as number) + paid
    })
  }
  const allLoaded = loaded.length === holdingsQueries.length
  const series = allLoaded ? withLivePoint(dates, valueOn, todayIso(), total) : { dates, values: valueOn }
  const paidIn = series.dates.map((_, i) => paidInOn[Math.min(i, paidInOn.length - 1)] ?? null)
  const period = periodReturn(series.values, paidIn)

  // 1D: the holdings' five-minute prices added up, ending at the live figure.
  const dayLine =
    range === "1D" && allLoaded
      ? portfolioIntraday(
          holdings.map((h) => ({ instrumentId: h.instrumentId, units: h.units, priceGbp: h.priceGbp })),
          intraday.data ?? [],
          cash
        )
      : null
  const dayShown = dayLine ? withLiveNow(dayLine, now, total) : null
  const dayMove = dayShown ? (dayShown.values.at(-1) ?? dayShown.baseline) - dayShown.baseline : 0

  const sorted = sortHoldings(holdings, sort)
  const sparkById = new Map(holdings.map((h, i) => [h.instrumentId, sparklines[i]?.data ?? []]))

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader eyebrow={EYEBROWS[view]} title="Live" actions={<MarketStrip />} />

      {canChooseView && (
        <Segmented options={VIEWS} value={view} onChange={setLiveView} label="Show" className="-mb-4 md:-mb-6" />
      )}

      <section aria-label="Value now" className="flex flex-col gap-2">
        <Money value={total} display className="text-[44px] leading-none tracking-[-0.02em] text-ink sm:text-[64px]" />
        <p className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-sm text-ink-muted">
          <DeltaChip amountGbp={dayChange} pct={changePct(invested, dayChange) ?? undefined} className="text-[15px]" />
          today
          <span aria-hidden="true">·</span>
          <span>
            {fromTrading212 ? "Trading 212 prices" : "Yahoo prices, delayed"}
            {pricedAt ? ` as of ${formatTime(pricedAt)}` : ""}
          </span>
        </p>
        {liveProblem && <p className="text-xs text-warn">Trading 212 live prices: {liveProblem.message}</p>}
        {unsyncedTrade && (
          <p className="text-xs text-ink-muted">
            Trading 212 shows a trade that isn&apos;t in Waymark yet. It appears here once the sync has brought it in.
          </p>
        )}
      </section>

      <section className="grid grid-cols-2 gap-x-8 gap-y-6 lg:grid-cols-4" aria-label="Summary">
        <StatTile
          label="Total return"
          value={<Money value={gain} whole />}
          hint={<DeltaChip amountGbp={gain} pct={cost > 0 ? gain / cost : undefined} className="text-xs" />}
        />
        <StatTile label="Invested" value={<Money value={invested} whole />} hint={`${holdings.length} holding${holdings.length === 1 ? "" : "s"}`} />
        <StatTile label="Cost" value={<Money value={cost} whole />} hint="What the holdings were bought for" />
        <StatTile label="Cash" value={<Money value={cash} whole />} hint={`${holdingsAccounts.length} account${holdingsAccounts.length === 1 ? "" : "s"}`} />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Value</CardTitle>
          <CardAction>
            <RangeFilter value={range} onChange={setRange} ranges={RANGES} />
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {range === "1D" ? (
            dayShown ? (
              <>
                <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-ink-muted">
                  <DeltaChip amountGbp={dayMove} pct={dayShown.baseline > 0 ? dayMove / dayShown.baseline : undefined} />
                  {dayShown.day === todayIso() ? "today" : `on ${formatDate(dayShown.day)}, the last trading day`}
                  <span className="text-xs">(dashed line: previous close)</span>
                </p>
                <AccountHistoryChart dates={dayShown.times} value={dayShown.values} height={300} fitToData intraday baseline={dayShown.baseline} />
              </>
            ) : (
              <p className="py-16 text-center text-sm text-ink-muted">
                {intraday.isPending || !allLoaded ? "Fetching today's prices…" : "No prices for today yet. Try a longer range."}
              </p>
            )
          ) : (
            <>
              {period && (
                <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-ink-muted">
                  <DeltaChip amountGbp={period.gainGbp ?? period.changeGbp} pct={period.pct ?? undefined} />
                  {period.gainGbp === null ? "change in value" : "return"} {RANGE_WORDS[range]}
                  {period.gainGbp !== null && <span className="text-xs">(after money paid in or taken out)</span>}
                </p>
              )}
              <AccountHistoryChart dates={series.dates} value={series.values} height={300} fitToData />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Holdings</CardTitle>
          <CardAction>
            <Segmented options={SORTS} value={sort} onChange={setSort} label="Sort holdings by" size="sm" />
          </CardAction>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {holdings.length === 0 ? (
            <p className="text-sm text-ink-muted">No holdings yet. Add them on an account&apos;s Holdings tab.</p>
          ) : (
            <table className="w-full text-sm sm:min-w-[720px]">
              <thead>
                <tr className="border-b border-ink text-xs text-ink-muted">
                  <th className="py-2 pr-3 text-left font-medium">Holding</th>
                  <th className="hidden py-2 pr-3 text-left font-medium sm:table-cell">30 days</th>
                  <th className="hidden py-2 pr-3 text-right font-medium sm:table-cell">Price</th>
                  <th className="py-2 pr-3 text-right font-medium">Today</th>
                  <th className="py-2 pr-3 text-right font-medium">Value</th>
                  <th className="hidden py-2 text-right font-medium sm:table-cell">Total return</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((h) => {
                  const closes = (sparkById.get(h.instrumentId) ?? []).map((p) => p.close_gbp)
                  return (
                    <tr key={h.instrumentId} className="border-b border-rule-soft align-middle">
                      <td className="py-3 pr-3">
                        <Link to={`/instruments/${h.instrumentId}`} className="font-mono-figures text-[13px] text-ink hover:underline">
                          {h.symbol}
                        </Link>
                        <p className="max-w-[130px] truncate text-xs text-ink-muted sm:max-w-[280px]" title={h.name}>
                          {h.name}
                        </p>
                        <p className="max-w-[130px] truncate text-xs text-ink-muted sm:max-w-none" title={h.accounts.join(", ")}>
                          {formatUnits(h.units)} units · {h.accounts.join(", ")}
                        </p>
                      </td>
                      <td className="hidden py-3 pr-3 sm:table-cell">
                        <Sparkline values={h.priceGbp > 0 ? [...closes, h.priceGbp] : closes} />
                      </td>
                      <td className="hidden py-3 pr-3 text-right sm:table-cell">
                        <Money value={h.priceGbp} className="text-ink" />
                        {h.isStale && <p className="text-xs text-warn">Old price</p>}
                      </td>
                      <td className="max-w-[92px] py-3 pr-3 text-right sm:max-w-none">
                        <DeltaChip
                          amountGbp={h.dayChangeGbp}
                          pct={h.dayChangePct ?? undefined}
                          className="justify-end text-[13px] whitespace-normal sm:whitespace-nowrap"
                        />
                      </td>
                      <td className="py-3 text-right sm:pr-3">
                        <Money value={h.valueGbp} className="text-ink" />
                        {/* Phones drop the return column; keep the figure under the value. */}
                        <DeltaChip amountGbp={h.gainGbp} className="block text-xs sm:hidden" />
                      </td>
                      <td className="hidden py-3 text-right sm:table-cell">
                        <DeltaChip amountGbp={h.gainGbp} pct={h.gainPct ?? undefined} className="text-[13px]" />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <section aria-label="Accounts" className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
        {holdingsAccounts.map((account) => (
          <Link key={account.id} to={`/accounts/${account.id}`} className="group/acct flex items-baseline gap-2.5">
            <span className="text-ink-2 group-hover/acct:text-ink group-hover/acct:underline">{account.name}</span>
            <Money value={account.value_gbp} whole className="text-ink" />
          </Link>
        ))}
      </section>
    </div>
  )
}
