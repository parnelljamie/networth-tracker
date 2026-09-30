import { useRef, useState } from "react"
import { PercentInput } from "@/components/PercentInput"
import { cn } from "@/lib/utils"

interface InlinePercentInputProps {
  /** Fraction, e.g. 0.045 for 4.5%. */
  value: number
  /** Called with the new fraction on blur or Enter, only when it actually changed. */
  onCommit: (value: number) => void
  className?: string
  "aria-label"?: string
}

/** A percentage shown as an editable field in place, saved when the user leaves it. */
export function InlinePercentInput({ value, onCommit, className, ...rest }: InlinePercentInputProps) {
  const [draft, setDraft] = useState<number | undefined>(value)
  const [lastValue, setLastValue] = useState(value)
  // Resync the draft when the saved value changes underneath (e.g. after a refetch).
  if (value !== lastValue) {
    setLastValue(value)
    setDraft(value)
  }

  const cancelled = useRef(false)

  function commit() {
    if (cancelled.current) {
      cancelled.current = false
      return
    }
    if (draft === undefined) {
      setDraft(value)
      return
    }
    // Percent → fraction division leaves float noise (5.966% → 0.05966000000000001).
    const rounded = Math.round(draft * 1e6) / 1e6
    if (Math.abs(rounded - value) > 1e-9) onCommit(rounded)
  }

  return (
    <PercentInput
      className={cn("w-24", className)}
      aria-label={rest["aria-label"]}
      value={draft}
      onChange={setDraft}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur()
        if (e.key === "Escape") {
          // Revert and skip the save that the following blur would otherwise make.
          cancelled.current = true
          setDraft(value)
          e.currentTarget.blur()
        }
      }}
    />
  )
}
