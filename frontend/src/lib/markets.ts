/** Whether the exchanges most holdings trade on are open, from their normal weekday hours.
 *  Bank holidays and early closes aren't known, so this is a guide, not a calendar. */

export interface Market {
  key: string
  label: string
  timeZone: string
  /** Minutes after local midnight. */
  opens: number
  closes: number
}

export const MARKETS: Market[] = [
  { key: "lse", label: "London", timeZone: "Europe/London", opens: 8 * 60, closes: 16 * 60 + 30 },
  { key: "us", label: "New York", timeZone: "America/New_York", opens: 9 * 60 + 30, closes: 16 * 60 },
]

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

/** The weekday and minutes after midnight at `now` in a market's own time zone. */
function localClock(now: Date, timeZone: string): { weekday: string; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ""
  return { weekday: get("weekday"), minutes: Number(get("hour")) * 60 + Number(get("minute")) }
}

export function isMarketOpen(market: Market, now: Date): boolean {
  const { weekday, minutes } = localClock(now, market.timeZone)
  return WEEKDAYS.includes(weekday) && minutes >= market.opens && minutes < market.closes
}
