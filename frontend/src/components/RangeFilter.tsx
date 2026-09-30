import { CHART_RANGES, type ChartRange } from "@/lib/dates"
import { cn } from "@/lib/utils"

interface RangeFilterProps {
  value: ChartRange
  onChange: (range: ChartRange) => void
  className?: string
  /** Which ranges to offer; defaults to all of CHART_RANGES. */
  ranges?: ChartRange[]
}

export function RangeFilter({ value, onChange, className, ranges = CHART_RANGES }: RangeFilterProps) {
  return (
    <div role="group" aria-label="Range" className={cn("inline-flex flex-wrap items-center gap-0.5 text-sm", className)}>
      {ranges.map((range) => (
        <button
          key={range}
          type="button"
          onClick={() => onChange(range)}
          aria-pressed={value === range}
          className={cn(
            "h-8 min-w-9 rounded-full px-2 text-[13px] transition-colors sm:min-w-10 sm:px-3",
            value === range ? "bg-ink font-semibold text-page" : "text-ink-2 hover:bg-muted hover:text-ink"
          )}
        >
          {range}
        </button>
      ))}
    </div>
  )
}
