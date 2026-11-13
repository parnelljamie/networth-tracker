import { useState } from "react"
import { Link, useParams } from "react-router"
import { useAccounts } from "@/api/hooks/useAccounts"
import { useHoldingsForAccounts } from "@/api/hooks/useHoldings"
import { useInstrument, useInstrumentPrices, useIntraday } from "@/api/hooks/useLive"
import { AccountHistoryChart } from "@/components/charts/AccountHistoryChart"
import { DeltaChip } from "@/components/DeltaChip"
import { EmptyState } from "@/components/EmptyState"
import { Money } from "@/components/Money"
import { PageHeader } from "@/components/PageHeader"
import { RangeFilter } from "@/components/RangeFilter"
import { StatTile } from "@/components/StatTile"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ALL_HISTORY_FROM, formatDate, formatTime, rangeStartIso, todayIso, type ChartRange } from "@/lib/dates"
import { formatUnits } from "@/lib/format"
import { instrumentIntraday, withLiveNow } from "@/lib/intraday"
import { changePct, combineHoldings, withLivePoint } from "@/lib/live"

const DAILY_RANGES: ChartRange[] = ["1W", "1M", "3M", "6M", "YTD", "1Y", "5Y", "All"]

const RANGE_WORDS: Record<ChartRange, string> = {
  "1D": "today",
  "1W": "over the past week",
  "1M": "over the past month",
  "3M": "over 3 months",
  "6M": "over 6 months",
  YTD: "this year",
  "1Y": "over the past year",
  "5Y": "over 5 years",
  All: "over the prices held",
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink">{children}</dd>
    </div>
  )
}

/** docs/05-ui.md "Instrument": one share or fund: its price now, how it has moved, and what
 *  the household holds of it. */
export function InstrumentPage() {
  const instrumentId = Number(useParams().id)
  const { data: instrument, isError } = useInstrument(instrumentId)
  const { data: accounts } = useAccounts()
  const listed = instrument?.price_source === "yahoo"
  const [chosenRange, setRange] = useState<ChartRange | null>(null)
  // A listed share opens on today; a fund priced by hand has no prices within a day.
  const range = chosenRange ?? (listed ? "1D" : "1Y")
  const ranges: ChartRange[] = listed ? ["1D", ...DAILY_RANGES] : DAILY_RANGES

  const holdingsAccounts = (accounts ?? []).filter((a) => a.valuation_method === "holdings")
  const holdingsQueries = useHoldingsForAccounts(holdingsAccounts.map((a) => a.id))
  const perAccount = holdingsQueries.flatMap((q, i) => {
    const position = q.data?.positions.find((p) => p.instrument.id === instrumentId)
    return position ? [{ account: holdingsAccounts[i], position }] : []
  })
  const holding = combineHoldings(
    perAccount.map(({ account, position }) => ({
      name: account.name,
      positions: [position],
    }))
  )[0]

  const dailyFrom = range === "1D" ? rangeStartIso("1W") : rangeStartIso(range)
  const [daily] = useInstrumentPrices(Number.isFinite(instrumentId) ? [instrumentId] : [], dailyFrom ?? ALL_HISTORY_FROM)
  const intraday = useIntraday([instrumentId], range === "1D" && listed)

  if (isError || !Number.isFinite(instrumentId)) {
    return (
      <div className="flex flex-col gap-10">
        <PageHeader eyebrow="Share or fund" title="Not found" />
        <EmptyState title="That share or fund isn't here" description="It may have been removed. Your holdings are on the Live page." />
      </div>
    )
  }
  if (!instrument) return null

  const closes = daily?.data ?? []
  const price = holding?.priceGbp ?? instrument.last_price_gbp ?? instrument.manual_price_gbp ?? closes.at(-1)?.close_gbp ?? 0
  const pricedAt = holding?.priceAt ?? instrument.last_price_at

  // Today's move per unit: from the holding when there is one (it follows a tracked fund too),
  // otherwise from the quote, and only when the quote's latest bar is today's.
  let dayChange: number | null = null
  if (holding && holding.units > 0) dayChange = holding.dayChangeGbp / holding.units
  else if (instrument.last_bar_date === todayIso() && instrument.last_price_gbp != null && instrument.prev_close_gbp != null) {
    dayChange = instrument.last_price_gbp - instrument.prev_close_gbp
  }

  const line = range === "1D" ? instrumentIntraday(intraday.data?.find((s) => s.instrument_id === instrumentId)) : null
  const dayLine = line && price > 0 ? withLiveNow(line, new Date(), price) : line
  const dailySeries = withLivePoint(
    closes.map((p) => p.date),
    closes.map((p) => p.close_gbp),
    todayIso(),
    price
  )
  const shown = range === "1D" ? (dayLine ? { dates: dayLine.times, values: dayLine.values } : { dates: [], values: [] }) : dailySeries
  const start = dayLine ? dayLine.baseline : shown.values[0]
  const end = shown.values.at(-1)
  const move = start !== undefined && end !== undefined && shown.values.length > 0 ? end - start : null
  const notToday = dayLine && dayLine.day !== todayIso()

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow={instrument.symbol}
        title={instrument.name}
        actions={
          <Link to="/live" className="text-sm text-ink-2 hover:text-ink hover:underline">
            All holdings
          </Link>
        }
      />

      <section aria-label="Price now" className="flex flex-col gap-2">
        <Money value={price} display className="text-[44px] leading-none tracking-[-0.02em] text-ink sm:text-[64px]" />
        <p className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 text-sm text-ink-muted">
          {dayChange !== null && (
            <>
              <DeltaChip amountGbp={dayChange} pct={changePct(price, dayChange) ?? undefined} className="text-[15px]" />
              today
              <span aria-hidden="true">·</span>
            </>
          )}
          <span>
            {listed ? "Price per unit" : "Price per unit, entered by hand"}
            {pricedAt ? ` as of ${formatDate(pricedAt)} ${formatTime(pricedAt)}` : ""}
          </span>
        </p>
        {holding?.isStale && <p className="text-xs text-warn">This price is old. It will update at the next refresh that reaches it.</p>}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Price</CardTitle>
          <CardAction>
            <RangeFilter value={range} onChange={setRange} ranges={ranges} />
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {move !== null && start !== undefined && (
            <p className="flex flex-wrap items-baseline gap-x-2 text-sm text-ink-muted">
              <DeltaChip amountGbp={move} pct={start > 0 ? move / start : undefined} />
              {notToday && dayLine ? `on ${formatDate(dayLine.day)}, the last day it traded` : RANGE_WORDS[range]}
              {range === "1D" && <span className="text-xs">(dashed line: previous close)</span>}
            </p>
          )}
          {range === "1D" && !dayLine ? (
            <p className="py-16 text-center text-sm text-ink-muted">
              {intraday.isPending ? "Fetching today's prices…" : "No prices for today yet. Try a longer range."}
            </p>
          ) : shown.dates.length === 0 ? (
            <p className="py-16 text-center text-sm text-ink-muted">No prices held for this range yet.</p>
          ) : (
            <AccountHistoryChart
              dates={shown.dates}
              value={shown.values}
              height={300}
              fitToData
              intraday={range === "1D"}
              baseline={dayLine?.baseline}
              label="Price"
            />
          )}
        </CardContent>
      </Card>

      {holding ? (
        <>
          <section className="grid grid-cols-2 gap-x-8 gap-y-6 lg:grid-cols-4" aria-label="Your holding">
            <StatTile label="Your holding" value={<Money value={holding.valueGbp} whole />} hint={`${formatUnits(holding.units)} units`} />
            <StatTile
              label="Total return"
              value={<Money value={holding.gainGbp} whole />}
              hint={<DeltaChip amountGbp={holding.gainGbp} pct={holding.gainPct ?? undefined} className="text-xs" />}
            />
            <StatTile label="Cost" value={<Money value={holding.costGbp} whole />} hint="What it was bought for" />
            <StatTile
              label="Average cost"
              value={<Money value={holding.units > 0 ? holding.costGbp / holding.units : 0} />}
              hint="Per unit"
            />
          </section>

          <Card>
            <CardHeader>
              <CardTitle>Where it is held</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ink text-xs text-ink-muted">
                    <th className="py-2 pr-3 text-left font-medium">Account</th>
                    <th className="py-2 pr-3 text-right font-medium">Units</th>
                    <th className="hidden py-2 pr-3 text-right font-medium sm:table-cell">Today</th>
                    <th className="py-2 pr-3 text-right font-medium">Value</th>
                    <th className="hidden py-2 text-right font-medium sm:table-cell">Total return</th>
                  </tr>
                </thead>
                <tbody>
                  {perAccount.map(({ account, position }) => (
                    <tr key={account.id} className="border-b border-rule-soft">
                      <td className="py-3 pr-3">
                        <Link to={`/accounts/${account.id}`} className="text-ink hover:underline">
                          {account.name}
                        </Link>
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-ink">{formatUnits(position.units)}</td>
                      <td className="hidden py-3 pr-3 text-right sm:table-cell">
                        <DeltaChip amountGbp={position.day_change_gbp} className="text-[13px]" />
                      </td>
                      <td className="py-3 pr-3 text-right">
                        <Money value={position.value_gbp} className="text-ink" />
                      </td>
                      <td className="hidden py-3 text-right sm:table-cell">
                        <DeltaChip
                          amountGbp={position.value_gbp - position.cost_basis_gbp}
                          pct={
                            position.cost_basis_gbp ? (position.value_gbp - position.cost_basis_gbp) / position.cost_basis_gbp : undefined
                          }
                          className="text-[13px]"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      ) : (
        <p className="text-sm text-ink-muted">You don&apos;t hold this at the moment.</p>
      )}

      <section aria-label="Details">
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 border-t border-border pt-4 sm:grid-cols-3 lg:grid-cols-6">
          <Detail label="Exchange">{instrument.exchange ?? "—"}</Detail>
          <Detail label="Quoted in">{instrument.quote_currency}</Detail>
          <Detail label="Type">{instrument.quote_type ?? "—"}</Detail>
          <Detail label="Asset class">{instrument.asset_class.replace("_", " ")}</Detail>
          <Detail label="ISIN">{instrument.isin ?? "—"}</Detail>
          <Detail label="Prices from">
            {listed ? "Yahoo" : instrument.tracks_instrument_id ? "By hand, following a listed fund" : "By hand"}
          </Detail>
        </dl>
      </section>
    </div>
  )
}
