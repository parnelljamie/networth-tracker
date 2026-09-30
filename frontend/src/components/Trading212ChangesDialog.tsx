import { useEffect, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { useHealth } from "@/api/hooks/useHealth"
import {
  type Trading212ChangesOut,
  useAcceptTrading212Changes,
  useTrading212Changes,
  useTrading212Links,
} from "@/api/hooks/useTrading212"
import { MatchImportInstruments } from "@/components/MatchImportInstruments"
import { Money } from "@/components/Money"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate } from "@/lib/dates"
import { formatUnits } from "@/lib/format"
import { dismissTrading212Changes, useDismissedTrading212Changes } from "@/lib/trading212Changes"

const TYPE_LABEL: Record<string, string> = {
  BUY: "Bought",
  SELL: "Sold",
  DIVIDEND: "Dividend",
  DEPOSIT: "Deposit",
  WITHDRAWAL: "Withdrawal",
  INTEREST: "Interest",
  FEE: "Fee",
  TAX: "Tax",
  TRANSFER_IN: "Transfer in",
  TRANSFER_OUT: "Transfer out",
  ADJUSTMENT: "Adjustment",
}

/** App-wide: when a Trading 212 sync brings changes to holdings (services/trading212_service.py
 * `pending_changes`), pop them up over whatever page is open, to accept in one click. "Not now"
 * puts it off for this session; Settings → Trading 212 can bring it back. PC only. */
export function Trading212ChangesDialog() {
  // Wait for health rather than assume the PC: the phone has no Trading 212 routes.
  const desktop = useHealth().data?.role === "desktop"
  const { data: links } = useTrading212Links(desktop)
  const pendingBatchIds = (links ?? [])
    .filter((l) => l.status === "needs_review" && l.pending_batch_id !== null)
    .map((l) => l.pending_batch_id!)
  const { data: changes } = useTrading212Changes(desktop ? pendingBatchIds : [])
  const dismissed = useDismissedTrading212Changes()

  // Say how a sync ended, wherever it was started from (Sync now, Update prices, the daily run).
  // Changes to accept speak for themselves: the popup opens.
  const previous = useRef<Map<number, string>>(new Map())
  useEffect(() => {
    for (const link of links ?? []) {
      const was = previous.current.get(link.account_id)
      previous.current.set(link.account_id, link.status)
      if (was !== "running" || link.status === "running") continue
      if (link.status === "up_to_date") toast.success("Trading 212: no new activity")
      else if (link.status === "synced")
        toast.success(`Trading 212: ${link.last_new_rows} new transaction${link.last_new_rows === 1 ? "" : "s"} added`)
      else if (link.status === "error") toast.error(`Trading 212 sync failed: ${link.status_message ?? "unknown error"}`)
    }
  }, [links])

  const current = (changes ?? []).find(
    (c) => pendingBatchIds.includes(c.batch_id) && !dismissed.has(c.batch_id)
  )

  return (
    <Dialog open={current !== undefined} onOpenChange={(open) => !open && current && dismissTrading212Changes(current.batch_id)}>
      {current && <ChangesContent key={current.batch_id} changes={current} />}
    </Dialog>
  )
}

function ChangesContent({ changes }: { changes: Trading212ChangesOut }) {
  const queryClient = useQueryClient()
  const accept = useAcceptTrading212Changes()
  const cashMoved = Math.abs(changes.cash_after_gbp - changes.cash_before_gbp) >= 0.005

  async function doAccept() {
    try {
      await accept.mutateAsync(changes.account_id)
      toast.success(`${changes.account_name} updated from Trading 212`)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not apply the Trading 212 changes"))
    }
  }

  return (
    <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>Trading 212: {changes.account_name}</DialogTitle>
        <DialogDescription>
          {changes.first_sync
            ? "Your Trading 212 history is ready to add. Check the holdings match what the Trading 212 app shows, then accept."
            : "New activity from Trading 212. Accept to update your holdings."}
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-4 text-sm">
        {changes.unmatched_instruments.length > 0 && (
          <MatchImportInstruments
            batchId={changes.batch_id}
            unmatched={changes.unmatched_instruments}
            onResolved={() => void queryClient.invalidateQueries({ queryKey: ["trading212", "changes"] })}
          />
        )}

        {(changes.holdings.length > 0 || cashMoved) && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted">
                <th className="py-1 pr-3 font-normal">Holding</th>
                <th className="py-1 pr-3 text-right font-normal">Now</th>
                <th className="py-1 pr-3 text-right font-normal">After</th>
                <th className="py-1 text-right font-normal">Avg cost after</th>
              </tr>
            </thead>
            <tbody>
              {changes.holdings.map((h, i) => (
                <tr key={h.instrument_id ?? i} className="border-t border-border">
                  <td className="py-1.5 pr-3">
                    <span className="text-ink">{h.name ?? h.symbol}</span>
                    {h.name && h.symbol && <span className="text-ink-muted"> · {h.symbol}</span>}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-ink-muted">{formatUnits(h.current_units)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-ink">{formatUnits(h.imported_units)}</td>
                  <td className="py-1.5 text-right">
                    <Money value={h.imported_avg_cost_gbp} />
                  </td>
                </tr>
              ))}
              {cashMoved && (
                <tr className="border-t border-border">
                  <td className="py-1.5 pr-3 text-ink">Cash</td>
                  <td className="py-1.5 pr-3 text-right text-ink-muted">
                    <Money value={changes.cash_before_gbp} />
                  </td>
                  <td className="py-1.5 pr-3 text-right text-ink">
                    <Money value={changes.cash_after_gbp} />
                  </td>
                  <td />
                </tr>
              )}
            </tbody>
          </table>
        )}

        {changes.transactions.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs text-ink-muted">
              {changes.transactions.length} transaction{changes.transactions.length === 1 ? "" : "s"}
            </p>
            <ul className="max-h-56 overflow-y-auto rounded-lg border border-border">
              {changes.transactions.map((t, i) => (
                <li key={i} className="flex items-baseline gap-3 border-t border-border px-2.5 py-1.5 first:border-t-0">
                  <span className="w-24 shrink-0 text-xs text-ink-muted">{formatDate(t.date)}</span>
                  <span className="min-w-0 flex-1 truncate text-ink">
                    {TYPE_LABEL[t.type] ?? t.type}
                    {(t.name ?? t.symbol) && <span className="text-ink-2"> · {t.name ?? t.symbol}</span>}
                    {Math.abs(t.units) > 1e-9 && (
                      <span className="text-ink-muted"> · {formatUnits(Math.abs(t.units))} units</span>
                    )}
                  </span>
                  {Math.abs(t.amount_gbp) >= 0.005 && <Money value={t.amount_gbp} className="shrink-0" />}
                </li>
              ))}
            </ul>
          </div>
        )}

        {changes.ledger_warnings.length > 0 && (
          <p className="text-warn">
            {changes.ledger_warnings[0]}
            {changes.ledger_warnings.length > 1 ? ` (and ${changes.ledger_warnings.length - 1} more)` : ""}
          </p>
        )}
        {changes.first_sync && (
          <p className="text-xs text-ink-muted">
            Any units or average costs you entered by hand for these holdings are replaced by the real history.
            You can undo this from the Import page.
          </p>
        )}
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => dismissTrading212Changes(changes.batch_id)} disabled={accept.isPending}>
          Not now
        </Button>
        <Button onClick={() => void doAccept()} disabled={!changes.ready || accept.isPending}>
          {accept.isPending ? "Updating…" : "Accept"}
        </Button>
      </div>
    </DialogContent>
  )
}
