import { describe, expect, it } from "vitest"
import { formatDelta, formatGBP, formatPct } from "./format"

describe("formatGBP", () => {
  it("formats positive amounts with thousands separators", () => {
    expect(formatGBP(48210.55)).toBe("£48,210.55")
  })

  it("uses a true minus sign for negatives", () => {
    expect(formatGBP(-1234.5)).toBe("−£1,234.50")
  })

  it("formats zero without a sign", () => {
    expect(formatGBP(0)).toBe("£0.00")
  })

  it("drops the pence when whole is set", () => {
    expect(formatGBP(587841.13, { whole: true })).toBe("£587,841")
    expect(formatGBP(587841.62, { whole: true })).toBe("£587,842")
    expect(formatGBP(-1234.5, { whole: true })).toBe("−£1,235")
    expect(formatGBP(0, { whole: true })).toBe("£0")
  })

  it("ignores whole when compact is set", () => {
    expect(formatGBP(48200, { compact: true, whole: true })).toBe("£48.2k")
  })

  it("compacts thousands and millions", () => {
    expect(formatGBP(48200, { compact: true })).toBe("£48.2k")
    expect(formatGBP(1230000, { compact: true })).toBe("£1.23m")
  })
})

describe("formatPct", () => {
  it("converts a fraction to a percentage string", () => {
    expect(formatPct(0.045)).toBe("4.50%")
    expect(formatPct(0.0044)).toBe("0.44%")
  })
})

describe("formatDelta", () => {
  it("marks a positive change with an up arrow", () => {
    expect(formatDelta(212.4, 0.0044)).toEqual({ direction: "up", text: "▲ £212.40 (0.44%)" })
  })

  it("marks a negative change with a down arrow and no leading minus", () => {
    expect(formatDelta(-212.4, -0.0044)).toEqual({ direction: "down", text: "▼ £212.40 (0.44%)" })
  })

  it("marks zero as flat", () => {
    expect(formatDelta(0, 0)).toEqual({ direction: "flat", text: "£0.00 (0.00%)" })
  })
})
