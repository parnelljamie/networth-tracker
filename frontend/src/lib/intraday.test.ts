import { describe, expect, it } from "vitest"
import { instrumentIntraday, londonDay, portfolioIntraday, withLiveNow, type IntradaySeries } from "./intraday"

const london: IntradaySeries = {
  instrument_id: 1,
  prev_close_gbp: 100,
  points: [
    { at: "2026-11-13T08:00:00", price_gbp: 101 },
    { at: "2026-11-13T08:05:00", price_gbp: 102 },
    { at: "2026-11-13T14:30:00", price_gbp: 103 },
  ],
}
const newYork: IntradaySeries = {
  instrument_id: 2,
  prev_close_gbp: 50,
  points: [{ at: "2026-11-13T14:30:00", price_gbp: 52 }],
}

describe("londonDay", () => {
  it("reads a backend timestamp as UTC and gives the London date", () => {
    expect(londonDay("2026-11-13T08:00:00")).toBe("2026-11-13")
    expect(londonDay("2026-07-01T23:30:00")).toBe("2026-07-02") // BST
  })
})

describe("instrumentIntraday", () => {
  it("keeps the latest day and measures from the previous close", () => {
    const line = instrumentIntraday({ ...london, points: [{ at: "2026-11-12T16:25:00", price_gbp: 99 }, ...london.points] })
    expect(line).toMatchObject({ day: "2026-11-13", baseline: 100, values: [101, 102, 103] })
    expect(instrumentIntraday({ ...london, points: [] })).toBeNull()
  })
})

describe("portfolioIntraday", () => {
  it("adds the holdings up at each time, holding a market at its previous close until it opens", () => {
    const line = portfolioIntraday(
      [
        { instrumentId: 1, units: 10, priceGbp: 103 },
        { instrumentId: 2, units: 4, priceGbp: 52 },
        { instrumentId: 3, units: 100, priceGbp: 2 }, // priced by hand: flat
      ],
      [london, newYork, { instrument_id: 3, prev_close_gbp: null, points: [] }],
      30
    )
    expect(line).toEqual({
      times: ["2026-11-13T08:00:00", "2026-11-13T08:05:00", "2026-11-13T14:30:00"],
      values: [1010 + 200 + 230, 1020 + 200 + 230, 1030 + 208 + 230],
      day: "2026-11-13",
      baseline: 1000 + 200 + 230,
    })
  })

  it("leaves a holding that last traded on an earlier day flat at its current price", () => {
    const friday = { ...newYork, points: [{ at: "2026-11-12T20:55:00", price_gbp: 51 }] }
    const line = portfolioIntraday(
      [
        { instrumentId: 1, units: 1, priceGbp: 103 },
        { instrumentId: 2, units: 1, priceGbp: 51 },
      ],
      [london, friday],
      0
    )
    expect(line?.values).toEqual([152, 153, 154])
    expect(line?.baseline).toBe(151)
  })

  it("has nothing to draw without any prices", () => {
    expect(portfolioIntraday([{ instrumentId: 3, units: 1, priceGbp: 2 }], [], 0)).toBeNull()
  })
})

describe("withLiveNow", () => {
  const line = instrumentIntraday(london)!

  it("ends today's line at the live figure", () => {
    const ended = withLiveNow(line, new Date("2026-11-13T15:00:00Z"), 104)
    expect(ended.values.at(-1)).toBe(104)
    expect(ended.times).toHaveLength(4)
  })

  it("leaves an earlier day's line alone", () => {
    expect(withLiveNow(line, new Date("2026-11-14T10:00:00Z"), 104)).toBe(line)
  })
})
