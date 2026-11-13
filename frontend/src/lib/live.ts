/** Maths for the Live page: the same instrument across accounts as one holding, a history
 *  series ending at the live value, and the return over a chart range. Pure functions. */

export interface LivePositionInput {
  instrument: { id: number; symbol: string; name: string }
  units: number
  cost_basis_gbp: number
  price_gbp: number
  price_at: string | null
  is_stale: boolean
  value_gbp: number
  day_change_gbp: number
}

export interface LiveHolding {
  instrumentId: number
  symbol: string
  name: string
  units: number
  priceGbp: number
  priceAt: string | null
  isStale: boolean
  valueGbp: number
  costGbp: number
  gainGbp: number
  /** null when there is no cost to measure against. */
  gainPct: number | null
  dayChangeGbp: number
  /** null when yesterday's value was zero. */
  dayChangePct: number | null
  accounts: string[]
}

/** A change as a fraction of the value it started from. */
export function changePct(valueNow: number, change: number): number | null {
  const before = valueNow - change
  return before ? change / before : null
}

export function combineHoldings(accounts: { name: string; positions: LivePositionInput[] }[]): LiveHolding[] {
  const byInstrument = new Map<number, LiveHolding>()
  for (const account of accounts) {
    for (const pos of account.positions) {
      const existing = byInstrument.get(pos.instrument.id)
      if (existing) {
        existing.units += pos.units
        existing.valueGbp += pos.value_gbp
        existing.costGbp += pos.cost_basis_gbp
        existing.dayChangeGbp += pos.day_change_gbp
        existing.isStale = existing.isStale || pos.is_stale
        existing.accounts.push(account.name)
      } else {
        byInstrument.set(pos.instrument.id, {
          instrumentId: pos.instrument.id,
          symbol: pos.instrument.symbol,
          name: pos.instrument.name,
          units: pos.units,
          priceGbp: pos.price_gbp,
          priceAt: pos.price_at,
          isStale: pos.is_stale,
          valueGbp: pos.value_gbp,
          costGbp: pos.cost_basis_gbp,
          gainGbp: 0,
          gainPct: null,
          dayChangeGbp: pos.day_change_gbp,
          dayChangePct: null,
          accounts: [account.name],
        })
      }
    }
  }
  return Array.from(byInstrument.values(), (h) => ({
    ...h,
    gainGbp: h.valueGbp - h.costGbp,
    gainPct: h.costGbp ? (h.valueGbp - h.costGbp) / h.costGbp : null,
    dayChangePct: changePct(h.valueGbp, h.dayChangeGbp),
  }))
}

export type LiveSort = "value" | "today" | "return"

export function sortHoldings(holdings: LiveHolding[], sort: LiveSort): LiveHolding[] {
  const key = (h: LiveHolding) =>
    sort === "today" ? (h.dayChangePct ?? 0) : sort === "return" ? (h.gainPct ?? 0) : h.valueGbp
  return [...holdings].sort((a, b) => key(b) - key(a))
}

/** End a daily series at the live value: today's point is replaced, or added when the series
 *  stops at an earlier day. Snapshots are only rewritten when prices refresh, so the last stored
 *  point can trail the figure in the page header. */
export function withLivePoint(
  dates: string[],
  values: number[],
  today: string,
  liveValue: number
): { dates: string[]; values: number[] } {
  if (dates.length === 0) return { dates, values }
  if (dates[dates.length - 1] === today) {
    return { dates, values: [...values.slice(0, -1), liveValue] }
  }
  if (dates[dates.length - 1] > today) return { dates, values }
  return { dates: [...dates, today], values: [...values, liveValue] }
}

export interface PeriodReturn {
  /** Change in value, including money paid in or taken out. */
  changeGbp: number
  /** Change in value less net money paid in: what the investments themselves made. null when
   *  contributions aren't known at both ends. */
  gainGbp: number | null
  /** `gainGbp` (or the plain change) over the starting value. */
  pct: number | null
}

export function periodReturn(values: number[], contributions: (number | null)[]): PeriodReturn | null {
  if (values.length < 2) return null
  const start = values[0]
  const end = values[values.length - 1]
  const changeGbp = end - start
  const paidStart = contributions[0]
  const paidEnd = contributions[contributions.length - 1]
  const known = paidStart != null && paidEnd != null && contributions.length === values.length
  const gainGbp = known ? changeGbp - (paidEnd - paidStart) : null
  return { changeGbp, gainGbp, pct: start > 0 ? (gainGbp ?? changeGbp) / start : null }
}
