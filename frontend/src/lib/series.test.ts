import { describe, expect, it } from "vitest"
import { projectedEndValue, regroupByCategory, sumHistories, sumProjectionAccounts } from "./series"

describe("sumHistories", () => {
  it("forward-fills each account before summing, so a partial update doesn't collapse the total (#19)", () => {
    const result = sumHistories([
      [
        { date: "2026-01-01", value_gbp: 100 },
        { date: "2026-02-01", value_gbp: 150 },
      ],
      [
        { date: "2026-01-01", value_gbp: 1000 },
        { date: "2026-03-01", value_gbp: 1100 },
      ],
    ])
    expect(result.dates).toEqual(["2026-01-01", "2026-02-01", "2026-03-01"])
    expect(result.values).toEqual([1100, 1150, 1250])
  })

  it("doesn't count an account before its first history point", () => {
    const result = sumHistories([
      [{ date: "2026-01-01", value_gbp: 100 }],
      [{ date: "2026-02-01", value_gbp: 50 }],
    ])
    expect(result.values).toEqual([100, 150])
  })

  it("handles no histories", () => {
    expect(sumHistories([])).toEqual({ dates: [], values: [] })
  })
})

describe("sumProjectionAccounts", () => {
  const byAccount = { "1": [10, 20, 30], "2": [1, 2, 3], "3": [100, 200, 300] }

  it("sums only the listed accounts", () => {
    expect(sumProjectionAccounts(byAccount, [1, 2], 3)).toEqual([11, 22, 33])
  })

  it("ignores unknown accounts and a missing projection", () => {
    expect(sumProjectionAccounts(byAccount, [99], 3)).toEqual([0, 0, 0])
    expect(sumProjectionAccounts(undefined, [1], 2)).toEqual([0, 0])
  })
})

describe("projectedEndValue", () => {
  it("returns the last projected value, or undefined", () => {
    expect(projectedEndValue({ "4": [1, 2, 3] }, 4)).toBe(3)
    expect(projectedEndValue({ "4": [] }, 4)).toBeUndefined()
    expect(projectedEndValue(null, 4)).toBeUndefined()
  })
})

describe("regroupByCategory", () => {
  const history = {
    dates: ["2026-01-01", "2026-02-01"],
    total: [0, 0],
    series: [
      { key: "1", label: "Current account", values: [1000, 1200] },
      { key: "2", label: "Savings", values: [5000, 5000] },
      { key: "3", label: "ISA", values: [20000, 21000] },
      { key: "4", label: "House", values: [300000, 300000] },
    ],
  }
  const liquid = [
    { id: 1, category: "cash" },
    { id: 2, category: "cash" },
    { id: 3, category: "investment" },
  ]

  it("sums the kept accounts per category and drops the rest", () => {
    expect(regroupByCategory(history, liquid)?.series).toEqual([
      { key: "cash", label: "cash", values: [6000, 6200] },
      { key: "investment", label: "investment", values: [20000, 21000] },
    ])
  })

  it("rebuilds the total from the kept accounts only", () => {
    expect(regroupByCategory(history, liquid)?.total).toEqual([26000, 27200])
  })

  it("passes through a missing history", () => {
    expect(regroupByCategory(undefined, liquid)).toBeUndefined()
  })
})
