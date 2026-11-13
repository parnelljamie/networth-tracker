import { describe, expect, it } from "vitest"
import { changePct, combineHoldings, periodReturn, sortHoldings, withLivePoint, type LivePositionInput } from "./live"

function position(id: number, symbol: string, overrides: Partial<LivePositionInput> = {}): LivePositionInput {
  return {
    instrument: { id, symbol, name: symbol },
    units: 10,
    cost_basis_gbp: 1000,
    price_gbp: 110,
    price_at: null,
    is_stale: false,
    value_gbp: 1100,
    day_change_gbp: 11,
    ...overrides,
  }
}

describe("combineHoldings", () => {
  it("merges the same instrument across accounts and recomputes its percentages", () => {
    const [vwrp, eqqq] = combineHoldings([
      { name: "ISA", positions: [position(1, "VWRP.L"), position(2, "EQQQ.L", { cost_basis_gbp: 0 })] },
      { name: "GIA", positions: [position(1, "VWRP.L", { units: 30, value_gbp: 3300, cost_basis_gbp: 3400, day_change_gbp: 33 })] },
    ])
    expect(vwrp).toMatchObject({ units: 40, valueGbp: 4400, costGbp: 4400, gainGbp: 0, gainPct: 0, dayChangeGbp: 44 })
    expect(vwrp.dayChangePct).toBeCloseTo(44 / 4356)
    expect(vwrp.accounts).toEqual(["ISA", "GIA"])
    expect(eqqq.gainPct).toBeNull() // no cost to measure against
  })
})

describe("sortHoldings", () => {
  it("orders by value, today's move or total return, largest first", () => {
    const holdings = combineHoldings([
      {
        name: "ISA",
        positions: [
          position(1, "A", { value_gbp: 500, cost_basis_gbp: 100, day_change_gbp: -5 }),
          position(2, "B", { value_gbp: 900, cost_basis_gbp: 890, day_change_gbp: 30 }),
        ],
      },
    ])
    expect(sortHoldings(holdings, "value").map((h) => h.symbol)).toEqual(["B", "A"])
    expect(sortHoldings(holdings, "today").map((h) => h.symbol)).toEqual(["B", "A"])
    expect(sortHoldings(holdings, "return").map((h) => h.symbol)).toEqual(["A", "B"])
  })
})

describe("changePct", () => {
  it("measures against the value before the change", () => {
    expect(changePct(110, 10)).toBeCloseTo(0.1)
    expect(changePct(10, 10)).toBeNull()
  })
})

describe("withLivePoint", () => {
  it("replaces today's stored point with the live value", () => {
    expect(withLivePoint(["2026-11-12", "2026-11-13"], [100, 101], "2026-11-13", 105)).toEqual({
      dates: ["2026-11-12", "2026-11-13"],
      values: [100, 105],
    })
  })

  it("adds today when the series stops earlier, and leaves an empty series alone", () => {
    expect(withLivePoint(["2026-11-12"], [100], "2026-11-13", 105)).toEqual({
      dates: ["2026-11-12", "2026-11-13"],
      values: [100, 105],
    })
    expect(withLivePoint([], [], "2026-11-13", 105)).toEqual({ dates: [], values: [] })
  })
})

describe("periodReturn", () => {
  it("takes money paid in out of the change in value", () => {
    expect(periodReturn([1000, 1300], [900, 1100])).toEqual({ changeGbp: 300, gainGbp: 100, pct: 0.1 })
  })

  it("falls back to the plain change when contributions aren't known", () => {
    expect(periodReturn([1000, 1300], [null, 1100])).toEqual({ changeGbp: 300, gainGbp: null, pct: 0.3 })
    expect(periodReturn([1000], [900])).toBeNull()
  })
})
