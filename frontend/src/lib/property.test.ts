import { describe, expect, it } from "vitest"
import type { ScheduleRowOut } from "@/api/hooks/useLoans"
import { fixEndsHint, monthlySampled, scheduleRowsToCsv, yearlySampled, yearlySampledSeries } from "./property"

function row(date: string, closing: number): ScheduleRowOut {
  return {
    date,
    annual_rate: 0.045,
    opening_balance: closing + 500,
    payment: 1000,
    interest: 500,
    principal: 500,
    overpayment: 0,
    closing_balance: closing,
  }
}

describe("yearlySampled", () => {
  it("keeps the last row of each calendar year", () => {
    const rows = [row("2026-11-01", 200_000), row("2026-12-01", 199_500), row("2027-01-01", 199_000)]
    expect(yearlySampled(rows)).toEqual([
      { date: "2026-12-01", balance: 199_500 },
      { date: "2027-01-01", balance: 199_000 },
    ])
  })
})

describe("monthlySampled", () => {
  it("keeps the last point of each month, in date order", () => {
    const result = monthlySampled(
      ["2026-01-01", "2026-01-15", "2026-01-31", "2026-02-10", "2026-02-20"],
      [1, 2, 3, 4, 5]
    )
    expect(result).toEqual({ dates: ["2026-01-31", "2026-02-20"], values: [3, 5] })
  })
})

describe("yearlySampledSeries", () => {
  it("keeps the last point per year, keyed by date", () => {
    const result = yearlySampledSeries(["2026-11-30", "2026-12-31", "2027-01-31"], [10, 20, 30])
    expect([...result]).toEqual([
      ["2026-12-31", 20],
      ["2027-01-31", 30],
    ])
  })

  it("skips dates with no value", () => {
    expect([...yearlySampledSeries(["2026-12-31", "2027-12-31"], [10])]).toEqual([["2026-12-31", 10]])
  })
})

describe("scheduleRowsToCsv", () => {
  it("writes a header and one line per row", () => {
    expect(scheduleRowsToCsv([row("2026-10-01", 199_500)]).split("\n")).toEqual([
      "Date,Rate,Opening balance,Payment,Interest,Principal,Overpayment,Closing balance",
      "2026-10-01,0.045,200000,1000,500,500,0,199500",
    ])
  })
})

describe("fixEndsHint", () => {
  it("describes the time left on the current fix", () => {
    const summary = { current_period: { label: "5y fix", end_date: "2028-03-01", days_left: 400 } }
    expect(fixEndsHint(summary as Parameters<typeof fixEndsHint>[0])).toBe("Fix ends in 1y 1m (1 Mar 2028)")
  })

  it("is undefined without a current fixed period", () => {
    expect(fixEndsHint(undefined)).toBeUndefined()
    const summary = { current_period: { label: null, end_date: null, days_left: null } }
    expect(fixEndsHint(summary as Parameters<typeof fixEndsHint>[0])).toBeUndefined()
  })
})
