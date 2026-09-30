import { useState } from "react"
import { toast } from "sonner"
import { useDeleteHolding, useHoldings, useSetCash, useSetHolding } from "@/api/hooks/useHoldings"
import {
  type InstrumentOut,
  type InstrumentSearchResultOut,
  useCreateInstrument,
  useInstruments,
} from "@/api/hooks/useInstruments"
import { DeltaChip } from "@/components/DeltaChip"
import { Money } from "@/components/Money"
import { InstrumentSearch } from "@/components/InstrumentSearch"
import { ManualInstrumentDialog } from "@/components/ManualInstrumentDialog"
import { ManualPriceDialog } from "@/components/ManualPriceDialog"
import { Pct } from "@/components/Pct"
import { StalenessBadge } from "@/components/StalenessBadge"
import { daysSince } from "@/lib/dates"
import { apiErrorMessage } from "@/lib/api-error"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function HoldingsTab({ accountId }: { accountId: number }) {
  const { data: holdings } = useHoldings(accountId)
  const setHolding = useSetHolding()
  const deleteHolding = useDeleteHolding()
  const setCash = useSetCash()
  const createInstrument = useCreateInstrument()

  const [editing, setEditing] = useState<
    { instrumentId: number; symbol?: string; name?: string; units: string; avgCost: string } | null
  >(null)
  const [editingCash, setEditingCash] = useState<string | null>(null)
  const [manualDialogOpen, setManualDialogOpen] = useState(false)
  const [manualQuery, setManualQuery] = useState("")
  const [pricing, setPricing] = useState<InstrumentOut | null>(null)
  const { data: instruments } = useInstruments()
  const symbolOf = (id: number | null | undefined) => (instruments ?? []).find((i) => i.id === id)?.symbol

  async function saveEdit() {
    if (!editing || editing.units.trim() === "" || editing.avgCost.trim() === "") return
    const units = Number(editing.units)
    const avgCost = Number(editing.avgCost)
    if (Number.isNaN(units) || Number.isNaN(avgCost)) return
    try {
      await setHolding.mutateAsync({ accountId, instrumentId: editing.instrumentId, units, avgCostGbp: avgCost })
      toast.success("Recorded as adjustment")
      setEditing(null)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not update the holding"))
    }
  }

  async function saveCash() {
    if (editingCash === null) return
    const cash = Number(editingCash)
    if (Number.isNaN(cash)) return
    try {
      await setCash.mutateAsync({ accountId, cashGbp: cash })
      setEditingCash(null)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not update cash"))
    }
  }

  async function addFromSearch(result: InstrumentSearchResultOut) {
    try {
      const instrument = await createInstrument.mutateAsync({ symbol: result.symbol, price_source: "yahoo" })
      setEditing({ instrumentId: instrument.id, symbol: instrument.symbol, name: instrument.name, units: "", avgCost: "" })
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not add that instrument"))
    }
  }

  if (!holdings) return <p className="text-sm text-ink-muted">Loading…</p>

  const editingHeldPosition = editing && holdings.positions.some((p) => p.instrument.id === editing.instrumentId)
  const pendingNewRow = editing && !editingHeldPosition ? editing : null

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-sm">
        <InstrumentSearch
          onSelect={addFromSearch}
          onAddManual={(query) => {
            setManualQuery(query)
            setManualDialogOpen(true)
          }}
        />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[46rem] text-sm [&_td+td]:pl-4 [&_th+th]:pl-4">
          <thead>
            <tr className="border-b border-border text-left text-xs text-ink-muted">
              <th className="py-2 font-normal">Instrument</th>
              <th className="py-2 text-right font-normal">Units</th>
              <th className="py-2 text-right font-normal">Avg cost</th>
              <th className="py-2 text-right font-normal">Price</th>
              <th className="py-2 text-right font-normal">Value</th>
              <th className="py-2 text-right font-normal">Gain</th>
              <th className="py-2 text-right font-normal">Today</th>
              <th className="py-2 text-right font-normal">Weight</th>
            </tr>
          </thead>
          <tbody>
            {holdings.positions.map((pos) => {
              const isEditing = editing?.instrumentId === pos.instrument.id
              return (
                <tr key={pos.instrument.id} className="border-b border-border">
                  <td className="py-2">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono-figures text-ink">{pos.instrument.symbol}</span>
                      {pos.instrument.price_source === "manual" && (
                        <button
                          type="button"
                          onClick={() => setPricing(pos.instrument)}
                          className="rounded bg-muted px-1 text-xs text-ink-muted hover:text-ink"
                          title="Set the price, or follow a listed fund"
                        >
                          {pos.instrument.tracks_instrument_id ? `follows ${symbolOf(pos.instrument.tracks_instrument_id) ?? "a fund"}` : "manual"}
                        </button>
                      )}
                      {pos.is_stale && (
                        <StalenessBadge
                          staleness="warn"
                          daysSince={pos.price_at ? daysSince(pos.price_at) : null}
                          prices
                        />
                      )}
                    </div>
                    <p className="text-xs text-ink-muted">{pos.instrument.name}</p>
                  </td>
                  <td className="py-2 text-right">
                    {isEditing ? (
                      <Input
                        autoFocus
                        className="w-24 text-right"
                        value={editing.units}
                        onChange={(e) => setEditing({ ...editing, units: e.target.value })}
                        onKeyDown={(e) => e.key === "Enter" && saveEdit()}
                      />
                    ) : (
                      <button
                        type="button"
                        className="tabular-nums hover:underline"
                        onClick={() =>
                          setEditing({
                            instrumentId: pos.instrument.id,
                            units: String(pos.units),
                            avgCost: String(pos.avg_cost_gbp),
                          })
                        }
                      >
                        {pos.units}
                      </button>
                    )}
                  </td>
                  <td className="py-2 text-right">
                    {isEditing ? (
                      <Input
                        className="w-24 text-right"
                        value={editing.avgCost}
                        onChange={(e) => setEditing({ ...editing, avgCost: e.target.value })}
                        onKeyDown={(e) => e.key === "Enter" && saveEdit()}
                      />
                    ) : (
                      <button
                        type="button"
                        className="tabular-nums hover:underline"
                        onClick={() =>
                          setEditing({
                            instrumentId: pos.instrument.id,
                            units: String(pos.units),
                            avgCost: String(pos.avg_cost_gbp),
                          })
                        }
                      >
                        <Money value={pos.avg_cost_gbp} />
                      </button>
                    )}
                  </td>
                  <td className="py-2 text-right tabular-nums text-ink-2">
                    <Money value={pos.price_gbp} />
                  </td>
                  <td className="py-2 text-right">
                    <Money value={pos.value_gbp} className="text-ink" />
                  </td>
                  <td className="py-2 text-right">
                    <DeltaChip amountGbp={pos.gain_gbp} pct={pos.gain_pct ?? undefined} />
                  </td>
                  <td className="py-2 text-right">
                    <DeltaChip amountGbp={pos.day_change_gbp} pct={pos.day_change_pct ?? undefined} />
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-1.5 w-12 rounded-full bg-muted">
                        <div
                          className="h-1.5 rounded-full bg-primary"
                          style={{ width: `${Math.min(100, pos.weight * 100)}%` }}
                        />
                      </div>
                      <Pct value={pos.weight} decimals={0} className="w-9 text-ink-muted" />
                    </div>
                  </td>
                  <td className="py-2 pl-2 text-right">
                    <button
                      type="button"
                      className="text-xs text-ink-muted hover:text-loss"
                      onClick={() => deleteHolding.mutate({ accountId, instrumentId: pos.instrument.id })}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              )
            })}
            {pendingNewRow && (
              <tr className="border-b border-border bg-muted/40">
                <td className="py-2">
                  <span className="font-mono-figures text-ink">{pendingNewRow.symbol}</span>
                  <p className="text-xs text-ink-muted">{pendingNewRow.name}</p>
                </td>
                <td className="py-2 text-right">
                  <Input
                    autoFocus
                    className="w-24 text-right"
                    placeholder="Units"
                    value={pendingNewRow.units}
                    onChange={(e) => setEditing({ ...pendingNewRow, units: e.target.value })}
                    onKeyDown={(e) => e.key === "Enter" && saveEdit()}
                  />
                </td>
                <td className="py-2 text-right">
                  <Input
                    className="w-24 text-right"
                    placeholder="Avg cost"
                    value={pendingNewRow.avgCost}
                    onChange={(e) => setEditing({ ...pendingNewRow, avgCost: e.target.value })}
                    onKeyDown={(e) => e.key === "Enter" && saveEdit()}
                  />
                </td>
                <td colSpan={4} />
                <td className="py-2 pl-2 text-right">
                  <Button size="sm" onClick={saveEdit}>
                    Save
                  </Button>
                </td>
              </tr>
            )}
            <tr className="border-b border-border">
              <td className="py-2 text-ink-2">Cash</td>
              <td colSpan={4} />
              <td className="py-2 text-right">
                {editingCash !== null ? (
                  <Input
                    autoFocus
                    className="w-28 text-right"
                    value={editingCash}
                    onChange={(e) => setEditingCash(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && saveCash()}
                    onBlur={saveCash}
                  />
                ) : (
                  <button type="button" className="hover:underline" onClick={() => setEditingCash(String(holdings.cash_gbp))}>
                    <Money value={holdings.cash_gbp} />
                  </button>
                )}
              </td>
              <td colSpan={2} />
            </tr>
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-border font-medium">
              <td className="py-2">Total</td>
              <td colSpan={2} />
              <td />
              <td className="py-2 text-right">
                <Money value={holdings.totals.value_gbp + holdings.cash_gbp} className="text-ink" />
              </td>
              <td className="py-2 text-right">
                <DeltaChip amountGbp={holdings.totals.gain_gbp} pct={holdings.totals.gain_pct ?? undefined} />
              </td>
              <td className="py-2 text-right">
                <DeltaChip
                  amountGbp={holdings.totals.day_change_gbp}
                  pct={holdings.totals.day_change_pct ?? undefined}
                />
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
        {holdings.positions.length === 0 && (
          <p className="py-4 text-center text-sm text-ink-muted">No holdings yet — search above to add one.</p>
        )}
      </div>

      <ManualPriceDialog instrument={pricing} onOpenChange={(open) => !open && setPricing(null)} />

      <ManualInstrumentDialog
        open={manualDialogOpen}
        onOpenChange={setManualDialogOpen}
        initialQuery={manualQuery}
        onCreated={(instrument) =>
          setEditing({ instrumentId: instrument.id, symbol: instrument.symbol, name: instrument.name, units: "", avgCost: "" })
        }
      />
    </div>
  )
}
