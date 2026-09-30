import { describe, expect, it } from "vitest"
import { ageAt, buildChartRows, niceStep, pointCount, timeTicks, toTime, valueAxis } from "./chartData"

describe("niceStep", () => {
  it("rounds up to 1, 2, 2.5, 5 or 10 × a power of ten", () => {
    expect(niceStep(0.8)).toBe(1)
    expect(niceStep(1.7)).toBe(2)
    expect(niceStep(2.3)).toBe(2.5)
    expect(niceStep(37_000)).toBe(50_000)
    expect(niceStep(61_000)).toBe(100_000)
  })

  it("falls back to 1 for zero or invalid input", () => {
    expect(niceStep(0)).toBe(1)
    expect(niceStep(Number.NaN)).toBe(1)
  })
})

describe("buildChartRows", () => {
  const dates = ["2026-01-01", "2026-01-02", "2026-01-03"]

  it("puts Total and each series on every history row", () => {
    const rows = buildChartRows(dates, [{ label: "Cash", values: [10, 20, 30] }], [10, 20, 30])
    expect(rows.map((r) => [r.date, r.Total, r.Cash])).toEqual([
      ["2026-01-01", 10, 10],
      ["2026-01-02", 20, 20],
      ["2026-01-03", 30, 30],
    ])
    expect(rows[0].t).toBe(new Date("2026-01-01").getTime())
  })

  it("leaves a series undrawn before its first non-zero value (#15)", () => {
    const rows = buildChartRows(dates, [{ label: "ISA", values: [0, 0, 500] }], [0, 0, 500])
    expect(rows.map((r) => r.ISA)).toEqual([null, null, 500])
  })

  it("keeps drawing a series at zero once it has had a value", () => {
    const rows = buildChartRows(dates, [{ label: "Card", values: [-50, 0, 0] }], [-50, 0, 0])
    expect(rows.map((r) => r.Card)).toEqual([-50, 0, 0])
  })

  it("never draws an all-zero series", () => {
    const rows = buildChartRows(dates, [{ label: "Empty", values: [0, 0, 0] }], [0, 0, 0])
    expect(rows.every((r) => r.Empty === null)).toBe(true)
  })

  it("joins the projection to the last history point and skips dates history covers", () => {
    const rows = buildChartRows(dates, [], [100, 110, 120], {
      dates: ["2026-01-03", "2026-02-03", "2026-03-03"],
      total: [120, 130, 140],
    })
    expect(rows).toHaveLength(5)
    expect(rows[2].Projected).toBe(120) // seeded from the last history Total
    expect(rows.slice(3).map((r) => [r.date, r.Projected, r.Total])).toEqual([
      ["2026-02-03", 130, undefined],
      ["2026-03-03", 140, undefined],
    ])
  })
})

describe("pointCount", () => {
  it("counts only numeric values, so a single-point series can be given a dot (#20)", () => {
    const rows = buildChartRows(["2026-01-01", "2026-01-02"], [{ label: "Car", values: [0, 9000] }], [0, 9000])
    expect(pointCount(rows, "Car")).toBe(1)
    expect(pointCount(rows, "Total")).toBe(2)
  })
})

describe("valueAxis", () => {
  const row = (values: Record<string, number>) => ({ date: "x", t: 0, ...values })

  it("stacked: spans the running sums of assets and debts, with zero on the axis", () => {
    const { domain, ticks } = valueAxis(
      [row({ Cash: 300_000, Property: 300_000, Mortgage: -200_000, Total: 400_000 })],
      ["Total", "Cash", "Property", "Mortgage"],
      true
    )
    expect(domain[0]).toBeLessThanOrEqual(-200_000)
    expect(domain[1]).toBeGreaterThanOrEqual(600_000)
    expect(ticks).toContain(0)
  })

  it("stacked: a debt too small to see doesn't drag the axis below zero", () => {
    const { domain } = valueAxis([row({ Cash: 600_000, Card: -500 })], ["Cash", "Card"], true)
    expect(domain[0]).toBe(0)
  })

  it("lines: fits the drawn range instead of starting at zero", () => {
    const { domain } = valueAxis([row({ Total: 500_000 }), row({ Total: 520_000 })], ["Total"], false)
    expect(domain[0]).toBeGreaterThan(0)
    expect(domain[0]).toBeLessThanOrEqual(500_000)
    expect(domain[1]).toBeGreaterThanOrEqual(520_000)
  })

  it("lines: never goes below zero, even with a debt line", () => {
    const { domain } = valueAxis([row({ Total: 100_000, Card: -2_000 })], ["Total", "Card"], false)
    expect(domain[0]).toBeGreaterThanOrEqual(0)
  })

  it("only considers the keys passed, so hidden series don't stretch the axis", () => {
    const data = [row({ Total: 100_000, Property: 900_000 })]
    expect(valueAxis(data, ["Total"], false).domain[1]).toBeLessThan(900_000)
  })

  it("ticks run from the domain minimum to maximum in equal steps", () => {
    const { domain, ticks } = valueAxis([row({ Total: 12_345 })], ["Total"], true)
    expect(ticks[0]).toBe(domain[0])
    expect(ticks[ticks.length - 1]).toBe(domain[1])
    const steps = new Set(ticks.slice(1).map((t, i) => t - ticks[i]))
    expect(steps.size).toBe(1)
  })
})

describe("timeTicks", () => {
  it("spreads the requested number of ticks evenly, ends included", () => {
    expect(timeTicks(0, 100)).toEqual([0, 25, 50, 75, 100])
  })

  it("returns a single tick for an empty range", () => {
    expect(timeTicks(50, 50)).toEqual([50])
  })
})

describe("ageAt", () => {
  const dob = "1995-06-14"

  it("gives whole years at years precision", () => {
    expect(ageAt(dob, toTime("2026-09-20"), "years")).toBe("31")
  })

  it("gives years and months at months precision", () => {
    expect(ageAt(dob, toTime("2026-09-20"), "months")).toBe("31y 3m")
  })

  it("turns the year over on the birthday, not before it", () => {
    expect(ageAt(dob, toTime("2026-06-13"), "months")).toBe("30y 11m")
    expect(ageAt(dob, toTime("2026-06-14"), "months")).toBe("31y 0m")
  })

  it("clamps to zero before birth rather than going negative", () => {
    expect(ageAt(dob, toTime("1990-01-01"), "months")).toBe("0y 0m")
  })
})
