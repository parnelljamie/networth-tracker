import { describe, expect, it } from "vitest"
import { daysAgoLabel, daysSince, formatDate, rangeStartIso, timeAgo } from "./dates"
import { birthdayAtAge, monthsUntil } from "./pension"

describe("formatDate", () => {
  it("formats as day month year", () => {
    expect(formatDate("2026-09-19")).toBe("19 Sep 2026")
  })

  it("shows a dash for an invalid date", () => {
    expect(formatDate("not a date")).toBe("—")
  })
})

describe("daysAgoLabel", () => {
  it("reads naturally for 0, 1 and many days", () => {
    expect(daysAgoLabel(0)).toBe("today")
    expect(daysAgoLabel(1)).toBe("1 day ago")
    expect(daysAgoLabel(12)).toBe("12 days ago")
  })
})

describe("timeAgo", () => {
  const now = new Date("2026-09-22T12:00:00Z")
  it("reads naturally at each scale", () => {
    expect(timeAgo("2026-09-22T11:59:40Z", now)).toBe("just now")
    expect(timeAgo("2026-09-22T11:55:00Z", now)).toBe("5 min ago")
    expect(timeAgo("2026-09-22T09:00:00Z", now)).toBe("3 h ago")
    expect(timeAgo("2026-09-20T12:00:00Z", now)).toBe("2 days ago")
  })
  it("reads a timestamp with no zone as UTC", () => {
    expect(timeAgo("2026-09-22T11:55:00.000000", now)).toBe("5 min ago")
    expect(timeAgo("2026-09-22T12:55:00+01:00", now)).toBe("5 min ago")
  })
})

describe("daysSince", () => {
  it("counts whole calendar days", () => {
    expect(daysSince("2026-09-15T08:00:00Z", new Date(2026, 8, 22, 18, 0))).toBe(7)
  })
  it("is 0 for today and never negative", () => {
    expect(daysSince("2026-09-22", new Date(2026, 8, 22, 9, 0))).toBe(0)
    expect(daysSince("2026-09-30", new Date(2026, 8, 22))).toBe(0)
  })
  it("is null for an unreadable date", () => {
    expect(daysSince("not a date")).toBeNull()
  })
})

describe("rangeStartIso", () => {
  const from = new Date(2026, 8, 19) // 19 Sep 2026, local time

  it("counts back from the given date", () => {
    expect(rangeStartIso("1W", from)).toBe("2026-09-12")
    expect(rangeStartIso("1M", from)).toBe("2026-08-19")
    expect(rangeStartIso("1Y", from)).toBe("2025-09-19")
    expect(rangeStartIso("5Y", from)).toBe("2021-09-19")
  })

  it("starts YTD on 1 January", () => {
    expect(rangeStartIso("YTD", from)).toBe("2026-01-01")
  })

  it("has no lower bound for All", () => {
    expect(rangeStartIso("All", from)).toBeUndefined()
  })
})

describe("birthdayAtAge", () => {
  it("adds whole years without timezone drift", () => {
    expect(birthdayAtAge("1990-03-05", 68)).toBe("2058-03-05")
  })
})

describe("monthsUntil", () => {
  const today = new Date(2026, 8, 19)

  it("counts whole calendar months", () => {
    expect(monthsUntil("2027-09-01", today)).toBe(12)
  })

  it("clamps to the projection endpoint's 1–600 range", () => {
    expect(monthsUntil("2020-01-01", today)).toBe(1)
    expect(monthsUntil("2200-01-01", today)).toBe(600)
  })
})
