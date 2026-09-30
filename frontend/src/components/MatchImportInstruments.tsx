import { toast } from "sonner"
import { useResolveImportInstruments, type PreviewOut } from "@/api/hooks/useImports"
import { useCreateInstrument } from "@/api/hooks/useInstruments"
import { InstrumentSearch } from "@/components/InstrumentSearch"
import { Button } from "@/components/ui/button"
import { apiErrorMessage } from "@/lib/api-error"

type Unmatched = PreviewOut["unmatched_instruments"][number]

/** Import step 2: pick the instrument for each row the importer couldn't match. The choice is
 * saved as an alias for the batch's profile (e.g. "Trading 212 API"), so later imports and syncs
 * match it by themselves. */
export function MatchImportInstruments({
  batchId,
  unmatched,
  onResolved,
}: {
  batchId: number
  unmatched: Unmatched[]
  onResolved: () => void
}) {
  const createInstrument = useCreateInstrument()
  const resolve = useResolveImportInstruments()
  const busy = createInstrument.isPending || resolve.isPending

  async function choose(item: Unmatched, symbol: string) {
    try {
      // Returns the existing instrument when the symbol is already tracked.
      const instrument = await createInstrument.mutateAsync({ symbol, price_source: "yahoo" })
      if (!instrument) return
      await resolve.mutateAsync({ batchId, payload: { resolutions: [{ key: item.key, instrument_id: instrument.id }] } })
      toast.success(`${item.symbol ?? item.name ?? "Instrument"} matched to ${instrument.symbol}`)
      onResolved()
    } catch (err) {
      toast.error(apiErrorMessage(err, `Could not use ${symbol}`))
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <p className="text-sm text-warn">
        {unmatched.length} instrument{unmatched.length === 1 ? "" : "s"} in this import {unmatched.length === 1 ? "isn't" : "aren't"} matched
        yet. Pick the listing to price {unmatched.length === 1 ? "it" : "each one"} from; any listing works, since prices
        are converted to pounds.
      </p>
      {unmatched.map((item) => (
        <div key={item.key} className="flex flex-col gap-2 border-t border-border pt-3 first:border-t-0 first:pt-0">
          <p className="text-sm text-ink">
            {item.name ?? item.symbol}
            <span className="text-ink-muted">
              {item.symbol ? ` · ${item.symbol}` : ""}
              {item.isin ? ` · ISIN ${item.isin}` : ""}
            </span>
          </p>
          {item.suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {item.suggestions.slice(0, 4).map((s) => (
                <Button
                  key={String(s.symbol)}
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => void choose(item, String(s.symbol))}
                >
                  {String(s.symbol)}
                  {s.exchange ? <span className="text-ink-muted"> · {String(s.exchange)}</span> : null}
                </Button>
              ))}
            </div>
          )}
          <InstrumentSearch
            placeholder={item.suggestions.length > 0 ? "Or search for another listing…" : "Search by symbol or name…"}
            onSelect={(result) => void choose(item, result.symbol)}
          />
        </div>
      ))}
    </div>
  )
}
