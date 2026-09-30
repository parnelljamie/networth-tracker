const MINUS = "−"

function formatCompactAmount(abs: number): string {
  if (abs >= 1_000_000) return `${(abs / 1_000_000).toFixed(2)}m`
  if (abs >= 1_000) return `${(abs / 1_000).toFixed(1)}k`
  return abs.toFixed(2)
}

/** `whole` drops the pence (docs/05-ui.md "Money"): dashboard balances are read at a glance and
 *  pence are noise there, so Overview’s figures round to whole pounds while account detail,
 *  transactions and every change figure keep them. Ignored when `compact` is set — compact is
 *  already rounded. */
export function formatGBP(value: number, opts: { compact?: boolean; whole?: boolean } = {}): string {
  if (!Number.isFinite(value)) return "—"
  const negative = value < 0
  const abs = Math.abs(value)
  const digits = opts.whole ? 0 : 2
  const body = opts.compact
    ? formatCompactAmount(abs)
    : abs.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits })
  return `${negative ? MINUS : ""}£${body}`
}

export function formatPct(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return "—"
  return `${(value * 100).toFixed(decimals)}%`
}

/** Holding units. Units are stored to 8 dp, but whole-share holdings should read "120", not
 *  "120.00000000" — so trailing zeros are dropped and fractional units keep up to 4 dp. */
export function formatUnits(value: number): string {
  if (!Number.isFinite(value)) return "—"
  return value.toLocaleString("en-GB", { maximumFractionDigits: 4 })
}

export interface FormattedDelta {
  direction: "up" | "down" | "flat"
  text: string
}

export function formatDelta(amountGbp: number, pct?: number): FormattedDelta {
  const direction: FormattedDelta["direction"] =
    amountGbp > 0 ? "up" : amountGbp < 0 ? "down" : "flat"
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : ""
  const amountText = formatGBP(Math.abs(amountGbp))
  const pctText = pct !== undefined ? ` (${formatPct(Math.abs(pct))})` : ""
  return { direction, text: `${arrow ? `${arrow} ` : ""}${amountText}${pctText}` }
}
