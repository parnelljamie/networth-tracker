import { cn } from "@/lib/utils"

interface SegmentedProps<T extends string | number | boolean | null> {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  label: string
  className?: string
  size?: "sm" | "md"
}

/** A joined row of pill buttons for one choice (scope, chart view, grouping). */
export function Segmented<T extends string | number | boolean | null>({
  options,
  value,
  onChange,
  label,
  className,
  size = "md",
}: SegmentedProps<T>) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex max-w-full flex-wrap", className)}>
      {options.map((o, i) => {
        const on = o.value === value
        return (
          <button
            key={String(o.value)}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "border border-border whitespace-nowrap transition-colors",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3.5 text-[13px]",
              i > 0 && "-ml-px",
              i === 0 && "rounded-l-full",
              i === options.length - 1 && "rounded-r-full",
              on ? "relative z-10 bg-card font-semibold text-ink" : "text-ink-2 hover:text-ink"
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
