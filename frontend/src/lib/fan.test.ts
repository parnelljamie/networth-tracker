import { describe, expect, it } from "vitest"
import { buildFanRows, fanSummary } from "./fan"

const mc = {
  dates: ["2026-09-19", "2036-09-19"],
  p10: [100, 150],
  p25: [100, 200],
  p50: [100, 250],
  p75: [100, 300],
  p90: [100, 400],
  deterministic: [100, 270],
}

describe("buildFanRows", () => {
  it("pairs the bands as [low, high] for range areas", () => {
    const rows = buildFanRows(mc)
    expect(rows[1]).toMatchObject({ outer: [150, 400], inner: [200, 300], median: 250, plan: 270 })
    expect(rows[1].t).toBe(new Date("2036-09-19").getTime())
  })

  it("shifts every series by the excluded amount", () => {
    const rows = buildFanRows(mc, [40, 60])
    expect(rows[0]).toMatchObject({ outer: [60, 60], median: 60, plan: 60 })
    expect(rows[1]).toMatchObject({ outer: [90, 340], inner: [140, 240], median: 190, plan: 210 })
  })
})

describe("fanSummary", () => {
  it("reads the 80% band and median at the horizon", () => {
    expect(fanSummary(buildFanRows(mc))).toEqual({ low: 150, median: 250, high: 400 })
  })

  it("is null with no data", () => {
    expect(fanSummary([])).toBeNull()
  })
})
