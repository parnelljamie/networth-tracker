import { describe, expect, it } from "vitest"
import { startPath } from "./startPage"

describe("startPath", () => {
  it("stays on the Overview by default", () => {
    expect(startPath("overview", "/pensions")).toBeNull()
  })

  it("opens the Live page when chosen", () => {
    expect(startPath("live", null)).toBe("/live")
  })

  it("returns to the last page, when there is one worth returning to", () => {
    expect(startPath("last", "/accounts/3")).toBe("/accounts/3")
    expect(startPath("last", "/")).toBeNull()
    expect(startPath("last", null)).toBeNull()
    expect(startPath("last", "https://example.com")).toBeNull()
  })
})
