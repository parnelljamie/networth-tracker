import { useEffect, useState } from "react"
import type { InstrumentSearchResultOut } from "@/api/hooks/useInstruments"
import { useInstrumentSearch } from "@/api/hooks/useInstruments"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface InstrumentSearchProps {
  onSelect: (result: InstrumentSearchResultOut) => void
  /** Offers "Add manual instrument…" when given. */
  onAddManual?: (query: string) => void
  placeholder?: string
}

export function InstrumentSearch({ onSelect, onAddManual, placeholder }: InstrumentSearchProps) {
  const [raw, setRaw] = useState("")
  const [debounced, setDebounced] = useState("")
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(raw), 300)
    return () => clearTimeout(timer)
  }, [raw])

  const { data: results, isFetching } = useInstrumentSearch(debounced)

  return (
    <div className="relative">
      <Input
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder ?? "Search by symbol or name…"}
      />
      {open && raw.trim().length > 0 && (
        <div className="absolute z-10 mt-1 w-full max-h-72 overflow-y-auto rounded-md border border-border bg-card shadow-lg">
          {isFetching && <p className="px-3 py-2 text-sm text-ink-muted">Searching…</p>}
          {!isFetching && (results ?? []).length === 0 && (
            <p className="px-3 py-2 text-sm text-ink-muted">No matches.</p>
          )}
          {(results ?? []).map((result) => (
            <button
              key={result.symbol}
              type="button"
              className={cn(
                "flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-muted"
              )}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onSelect(result)
                setOpen(false)
                setRaw("")
              }}
            >
              <span className="font-mono-figures text-ink">
                {result.symbol} <span className="text-ink-muted">· {result.exchange ?? "—"}</span>
              </span>
              <span className="text-ink-muted text-xs">{result.name}</span>
            </button>
          ))}
          {onAddManual && (
            <button
              type="button"
              className="w-full border-t border-border px-3 py-2 text-left text-sm text-primary hover:bg-muted"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onAddManual(raw)
                setOpen(false)
              }}
            >
              Add manual instrument…
            </button>
          )}
        </div>
      )}
    </div>
  )
}
