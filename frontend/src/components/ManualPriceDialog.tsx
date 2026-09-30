import { useState } from "react"
import { toast } from "sonner"
import {
  type InstrumentOut,
  useCreateInstrument,
  useInstruments,
  useUpdateInstrument,
} from "@/api/hooks/useInstruments"
import { DateInput } from "@/components/DateInput"
import { InstrumentSearch } from "@/components/InstrumentSearch"
import { MoneyInput } from "@/components/MoneyInput"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { apiErrorMessage } from "@/lib/api-error"

/** A manual instrument's stated price, and optionally a listed fund whose daily moves carry it
 * forward between stated prices (services/price_service.py `_manual_price_gbp`): e.g. pension
 * units priced from statements, following the listed share class of the same fund. */
export function ManualPriceDialog({
  instrument,
  onOpenChange,
}: {
  instrument: InstrumentOut | null
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={instrument !== null} onOpenChange={onOpenChange}>
      {instrument && <ManualPriceForm key={instrument.id} instrument={instrument} onDone={() => onOpenChange(false)} />}
    </Dialog>
  )
}

function ManualPriceForm({ instrument, onDone }: { instrument: InstrumentOut; onDone: () => void }) {
  const { data: instruments } = useInstruments()
  const createInstrument = useCreateInstrument()
  const update = useUpdateInstrument()
  const [price, setPrice] = useState<number | undefined>(instrument.manual_price_gbp ?? undefined)
  const [priceDate, setPriceDate] = useState<string | undefined>(instrument.manual_price_date ?? undefined)
  const [tracksId, setTracksId] = useState<number | null>(instrument.tracks_instrument_id ?? null)
  const [tracksLabel, setTracksLabel] = useState<string | null>(null)

  const tracked = (instruments ?? []).find((i) => i.id === tracksId)
  const busy = createInstrument.isPending || update.isPending

  async function follow(symbol: string) {
    try {
      // Returns the existing instrument when the symbol is already tracked.
      const target = await createInstrument.mutateAsync({ symbol, price_source: "yahoo" })
      if (!target) return
      setTracksId(target.id)
      setTracksLabel(`${target.name} · ${target.symbol}`)
    } catch (err) {
      toast.error(apiErrorMessage(err, `Could not use ${symbol}`))
    }
  }

  async function save() {
    try {
      await update.mutateAsync({
        id: instrument.id,
        payload: { manual_price_gbp: price ?? null, manual_price_date: priceDate ?? null, tracks_instrument_id: tracksId },
      })
      toast.success("Price saved. History is being recalculated.")
      onDone()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save the price"))
    }
  }

  return (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{instrument.name}</DialogTitle>
        <DialogDescription>Priced by hand, e.g. from statements.</DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-4 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>Price per unit</Label>
            <MoneyInput value={price} onChange={setPrice} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="manual-price-date">As of</Label>
            <DateInput id="manual-price-date" value={priceDate} onChange={setPriceDate} />
          </div>
        </div>
        <p className="-mt-2 text-xs text-ink-muted">Imported statements add dated unit prices too; the latest one wins.</p>

        <div className="flex flex-col gap-1.5">
          <Label>Follow the daily moves of</Label>
          {tracksId !== null ? (
            <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2">
              <span className="text-ink">
                {tracksLabel ?? (tracked ? `${tracked.name} · ${tracked.symbol}` : "A listed fund")}
              </span>
              <Button variant="ghost" size="sm" onClick={() => setTracksId(null)} disabled={busy}>
                Stop
              </Button>
            </div>
          ) : (
            <InstrumentSearch placeholder="Search for the listed fund…" onSelect={(r) => void follow(r.symbol)} />
          )}
          <p className="text-xs text-ink-muted">
            Between stated prices, the value moves by the same percentage as this fund, and resets to the real unit
            price at each new statement. Use the same fund in a class with live prices; the unit prices don't need
            to match.
          </p>
        </div>
      </div>

      <DialogFooter>
        <Button onClick={() => void save()} disabled={busy || price === undefined}>
          Save
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
