import { parseUtc } from "@/lib/dates"

/** Maths for the 1D charts: five-minute prices per instrument turned into one value line for a
 *  set of holdings. Pure functions. */

export interface IntradaySeries {
  instrument_id: number
  prev_close_gbp: number | null
  points: { at: string; price_gbp: number }[]
}

export interface IntradayHolding {
  instrumentId: number
  units: number
  /** The price the holding is valued at now. */
  priceGbp: number
}

export interface IntradayLine {
  /** Backend timestamps (UTC), oldest first. */
  times: string[]
  values: number[]
  /** The London calendar day the line covers: the latest day any holding traded. */
  day: string
  /** Value at the previous close, the level the day's move is measured from. */
  baseline: number
}

const LONDON_DAY = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/London",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
})

/** The London calendar day (YYYY-MM-DD) of a backend timestamp. */
export function londonDay(at: string): string {
  return LONDON_DAY.format(parseUtc(at))
}

/** One instrument's prices over its latest trading day. */
export function instrumentIntraday(series: IntradaySeries | undefined): IntradayLine | null {
  if (!series || series.points.length === 0) return null
  const day = londonDay(series.points[series.points.length - 1].at)
  const points = series.points.filter((p) => londonDay(p.at) === day)
  return {
    times: points.map((p) => p.at),
    values: points.map((p) => p.price_gbp),
    day,
    baseline: series.prev_close_gbp ?? points[0].price_gbp,
  }
}

/** The holdings' combined value through the latest trading day. A holding with no prices for
 *  that day (a fund priced by hand, or a market that hasn't opened yet) stays flat at the price
 *  it is valued at now; one that has yet to trade sits at its previous close until it does. */
export function portfolioIntraday(holdings: IntradayHolding[], series: IntradaySeries[], cashGbp: number): IntradayLine | null {
  const byId = new Map(series.map((s) => [s.instrument_id, instrumentIntraday(s)]))
  const lines = holdings.map((h) => byId.get(h.instrumentId) ?? null)
  const day = lines.reduce<string | null>((latest, line) => (line && (latest === null || line.day > latest) ? line.day : latest), null)
  if (day === null) return null

  let baseline = cashGbp
  const moving: {
    units: number
    line: IntradayLine
    next: number
    price: number
  }[] = []
  let flat = cashGbp
  holdings.forEach((h, i) => {
    const line = lines[i]
    if (line && line.day === day) {
      moving.push({ units: h.units, line, next: 0, price: line.baseline })
      baseline += h.units * line.baseline
    } else {
      flat += h.units * h.priceGbp
      baseline += h.units * h.priceGbp
    }
  })

  const times = Array.from(new Set(moving.flatMap((m) => m.line.times))).sort()
  const values = times.map((t) => {
    let total = flat
    for (const m of moving) {
      while (m.next < m.line.times.length && m.line.times[m.next] <= t) {
        m.price = m.line.values[m.next]
        m.next += 1
      }
      total += m.units * m.price
    }
    return total
  })
  return { times, values, day, baseline }
}

/** End the line at the figure shown now, when the line is for today. */
export function withLiveNow(line: IntradayLine, now: Date, liveValue: number): IntradayLine {
  const at = now.toISOString()
  if (londonDay(at) !== line.day || line.times.length === 0) return line
  if (parseUtc(line.times[line.times.length - 1]).getTime() >= now.getTime()) return line
  return {
    ...line,
    times: [...line.times, at],
    values: [...line.values, liveValue],
  }
}
