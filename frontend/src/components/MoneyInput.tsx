import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface MoneyInputProps {
  value: number | undefined
  onChange: (value: number | undefined) => void
  placeholder?: string
  className?: string
  id?: string
  "aria-label"?: string
}

export function MoneyInput({ value, onChange, placeholder, className, id, "aria-label": ariaLabel }: MoneyInputProps) {
  return (
    <div className={cn("relative", className)}>
      <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-muted text-sm">
        £
      </span>
      <Input
        id={id}
        aria-label={ariaLabel}
        type="number"
        step="0.01"
        inputMode="decimal"
        className="pl-6 tabular-nums"
        placeholder={placeholder ?? "0.00"}
        value={value ?? ""}
        onChange={(e) => {
          const raw = e.target.value
          onChange(raw === "" ? undefined : Number(raw))
        }}
      />
    </div>
  )
}
