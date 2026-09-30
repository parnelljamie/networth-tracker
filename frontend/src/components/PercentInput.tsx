import type React from "react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface PercentInputProps {
  /** Fraction, e.g. 0.045 for 4.5%. */
  value: number | undefined
  onChange: (value: number | undefined) => void
  className?: string
  id?: string
  disabled?: boolean
  onBlur?: () => void
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void
  "aria-label"?: string
}

export function PercentInput({ value, onChange, className, id, disabled, onBlur, onKeyDown, ...rest }: PercentInputProps) {
  return (
    <div className={cn("relative", className)}>
      <Input
        id={id}
        disabled={disabled}
        onBlur={onBlur}
        onKeyDown={onKeyDown}
        aria-label={rest["aria-label"]}
        type="number"
        step="0.01"
        inputMode="decimal"
        className="pr-7 tabular-nums"
        placeholder="0.00"
        value={value === undefined ? "" : Number((value * 100).toFixed(2))}
        onChange={(e) => {
          const raw = e.target.value
          onChange(raw === "" ? undefined : Number(raw) / 100)
        }}
      />
      <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-ink-muted text-sm">
        %
      </span>
    </div>
  )
}
