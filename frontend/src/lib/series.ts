/** Series maths shared by the household category pages (Pensions, Investments). Pure functions —
 *  no hooks, no formatting. */

export interface DatedValue {
  date: string
  value_gbp: number
}

/**
 * Sum several per-account histories onto one timeline. There is no per-category history endpoint,
 * so the category pages fetch a handful of `/accounts/{id}/history` series and combine them here.
 *
 * Accounts are valued on different dates, so each series is forward-filled from its own last
 * known value before summing — otherwise a month where only one account was updated would show
 * the household total collapsing to that one account.
 */
export function sumHistories(histories: DatedValue[][]): { dates: string[]; values: number[] } {
  const dates = Array.from(new Set(histories.flatMap((h) => h.map((p) => p.date)))).sort()
  if (dates.length === 0) return { dates: [], values: [] }

  const values = new Array<number>(dates.length).fill(0)
  for (const history of histories) {
    const byDate = new Map(history.map((p) => [p.date, p.value_gbp]))
    const firstDate = history[0]?.date
    let last = 0
    dates.forEach((d, i) => {
      last = byDate.get(d) ?? last
      // Don't let an account contribute before it had any history at all.
      if (firstDate !== undefined && d >= firstDate) values[i] += last
    })
  }
  return { dates, values }
}

/**
 * Sum the `by_account` series of a projection over just the accounts a page owns, giving that
 * page its own projected total without a dedicated endpoint. `by_account` is keyed by account id
 * as a string; values are aligned to the projection's `dates`.
 */
export function sumProjectionAccounts(
  byAccount: Record<string, number[]> | null | undefined,
  accountIds: number[],
  pointCount: number
): number[] {
  const values = new Array<number>(pointCount).fill(0)
  if (!byAccount) return values
  for (const id of accountIds) {
    const series = byAccount[String(id)]
    if (!series) continue
    for (let i = 0; i < pointCount; i++) values[i] += series[i] ?? 0
  }
  return values
}

/** The last point of an account's projected series, i.e. its value at the projection horizon. */
export function projectedEndValue(
  byAccount: Record<string, number[]> | null | undefined,
  accountId: number
): number | undefined {
  const series = byAccount?.[String(accountId)]
  if (!series || series.length === 0) return undefined
  return series[series.length - 1]
}

export interface GroupedHistory {
  dates: string[]
  total: number[]
  series: { key: string; label: string; values: number[] }[]
}

/**
 * Regroup a per-account history (series keyed by account id) into one series per category,
 * keeping only the given accounts — e.g. the Overview's liquid-only view. The total is rebuilt
 * from the kept accounts, so it matches the sum of the series drawn.
 */
export function regroupByCategory(
  byAccount: GroupedHistory | undefined,
  accounts: { id: number; category: string }[]
): GroupedHistory | undefined {
  if (!byAccount) return undefined
  const categoryById = new Map(accounts.map((a) => [String(a.id), a.category]))
  const byCategory = new Map<string, number[]>()
  for (const s of byAccount.series) {
    const category = categoryById.get(s.key)
    if (!category) continue
    const values = byCategory.get(category) ?? byAccount.dates.map(() => 0)
    s.values.forEach((v, i) => (values[i] += v))
    byCategory.set(category, values)
  }
  const series = [...byCategory].map(([key, values]) => ({ key, label: key, values }))
  const total = byAccount.dates.map((_, i) => series.reduce((sum, s) => sum + (s.values[i] ?? 0), 0))
  return { dates: byAccount.dates, total, series }
}
