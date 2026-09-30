import { formatGBP } from "@/lib/format"
import { usePrivacyMode } from "@/lib/privacy"
import { cn } from "@/lib/utils"

interface MoneyProps {
  value: number
  compact?: boolean
  /** Round to whole pounds — Overview's balances and totals. See `formatGBP`. */
  whole?: boolean
  /**
   * Hero treatment (docs/05-ui.md "Type"): the Newsreader serif with proportional digits, for a
   * big standalone figure. Otherwise the amount inherits its parent's face with tabular digits,
   * so a figure in a serif stat tile stays serif and a table cell stays in the UI sans.
   */
  display?: boolean
  className?: string
}

export function Money({ value, compact, whole, display, className }: MoneyProps) {
  const privacy = usePrivacyMode()
  const text = privacy ? "£•••••" : formatGBP(value, { compact, whole })
  return (
    <span
      className={cn(display ? "font-heading" : "tabular-nums", className)}
      aria-hidden={privacy}
    >
      {text}
    </span>
  )
}
