import { describe, expect, it } from "vitest"
import { isMarketOpen, MARKETS } from "./markets"

const [london, newYork] = MARKETS

describe("isMarketOpen", () => {
  it("follows each exchange's own clock, summer and winter", () => {
    // Friday 13 Nov 2026 (GMT / EST)
    expect(isMarketOpen(london, new Date("2026-11-13T07:59:00Z"))).toBe(false)
    expect(isMarketOpen(london, new Date("2026-11-13T08:00:00Z"))).toBe(true)
    expect(isMarketOpen(london, new Date("2026-11-13T16:30:00Z"))).toBe(false)
    expect(isMarketOpen(newYork, new Date("2026-11-13T14:29:00Z"))).toBe(false)
    expect(isMarketOpen(newYork, new Date("2026-11-13T14:30:00Z"))).toBe(true)
    expect(isMarketOpen(newYork, new Date("2026-11-13T21:00:00Z"))).toBe(false)
    // Wednesday 1 Jul 2026 (BST / EDT): an hour earlier in UTC
    expect(isMarketOpen(london, new Date("2026-07-01T07:00:00Z"))).toBe(true)
    expect(isMarketOpen(newYork, new Date("2026-07-01T13:30:00Z"))).toBe(true)
    expect(isMarketOpen(newYork, new Date("2026-07-01T20:00:00Z"))).toBe(false)
  })

  it("is closed at the weekend", () => {
    expect(isMarketOpen(london, new Date("2026-11-14T10:00:00Z"))).toBe(false)
    expect(isMarketOpen(newYork, new Date("2026-11-15T15:00:00Z"))).toBe(false)
  })
})
