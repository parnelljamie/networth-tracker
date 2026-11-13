import { describe, expect, it } from "vitest"
import { accountsInView, hasBothKinds } from "./liveView"

const isa = { id: 1, category: "investment" }
const sipp = { id: 2, category: "pension" }

describe("accountsInView", () => {
  it("shows only the chosen kind of account", () => {
    expect(accountsInView([isa, sipp], "investments")).toEqual({ view: "investments", accounts: [isa] })
    expect(accountsInView([isa, sipp], "pensions")).toEqual({ view: "pensions", accounts: [sipp] })
    expect(accountsInView([isa, sipp], "all")).toEqual({ view: "all", accounts: [isa, sipp] })
  })

  it("falls back to everything when the chosen kind has no accounts", () => {
    expect(accountsInView([isa], "pensions")).toEqual({ view: "all", accounts: [isa] })
  })
})

describe("hasBothKinds", () => {
  it("is true only when there is a choice to make", () => {
    expect(hasBothKinds([isa, sipp])).toBe(true)
    expect(hasBothKinds([isa])).toBe(false)
    expect(hasBothKinds([sipp])).toBe(false)
  })
})
