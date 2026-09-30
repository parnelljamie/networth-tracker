/** Pension date maths shared by the Pensions page. */

/** The projection endpoint's upper bound (50 years), matching the Projections page's horizon. */
export const MAX_PROJECTION_MONTHS = 600

/**
 * The date a person turns `age`, as an ISO "YYYY-MM-DD" string.
 *
 * The "YYYY-MM-DD" input is parsed manually rather than via `new Date()` so a browser timezone
 * behind UTC can't shift the result back by a day — the same deliberate choice the Person page's
 * pensions tab made.
 */
export function birthdayAtAge(dateOfBirth: string, age: number): string {
  const [y, m, d] = dateOfBirth.split("-").map(Number)
  return `${y + age}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`
}

/**
 * Whole months from today until `isoDate`, clamped to the projection endpoint's 1–600 range so a
 * person already past the date still gets a usable (minimum) projection rather than an error.
 */
export function monthsUntil(isoDate: string, today: Date = new Date()): number {
  const [y, m] = isoDate.split("-").map(Number)
  const months = (y - today.getFullYear()) * 12 + (m - 1 - today.getMonth())
  return Math.max(1, Math.min(MAX_PROJECTION_MONTHS, months))
}
