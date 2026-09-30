import { useEffect, useRef, useState } from "react"
import { Input } from "@/components/ui/input"

interface DateInputProps {
  value: string | undefined
  onChange: (value: string | undefined) => void
  className?: string
  id?: string
}

export function DateInput({ value, onChange, className, id }: DateInputProps) {
  // Local buffer so a round-tripped save (parent re-renders with a new `value`
  // prop once the mutation resolves) doesn't reset the native date input's
  // internal per-segment editing state while the user is still typing — that
  // reset is what causes a partially typed year like "1985" to commit early
  // as something like "0009".
  const [local, setLocal] = useState(value ?? "")
  const lastEmitted = useRef(value)

  useEffect(() => {
    if (value !== lastEmitted.current) {
      setLocal(value ?? "")
      lastEmitted.current = value
    }
  }, [value])

  return (
    <Input
      id={id}
      type="date"
      className={className}
      value={local}
      onChange={(e) => {
        const next = e.target.value
        setLocal(next)
        const emitted = next === "" ? undefined : next
        lastEmitted.current = emitted
        onChange(emitted)
      }}
    />
  )
}
